"""Raster ingestion, validation and pair alignment (Rasterio / OpenCV)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.transform import Affine, array_bounds
from rasterio.warp import reproject, transform_bounds

ALLOWED_EXT = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
LEVIR_GSD_M = 0.5  # LEVIR-CD ground sampling distance (Google Earth imagery, 0.5 m/px)


class RasterError(ValueError):
    pass


@dataclass
class RasterInfo:
    width: int
    height: int
    band_count: int
    georeferenced: bool
    crs: str | None = None
    transform: list[float] | None = None
    bounds_wgs84: list[float] | None = None
    pixel_size_m: float | None = None
    nodata_fraction: float = 0.0
    meta: dict = field(default_factory=dict)


def sniff_type(path: Path) -> str:
    """Verify actual file content, not just the extension."""
    with open(path, "rb") as f:
        head = f.read(12)
    if head.startswith(b"\x89PNG"): return "png"
    if head.startswith(b"\xff\xd8\xff"): return "jpeg"
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"): return "tiff"
    raise RasterError("Unsupported or corrupt file: content is not PNG, JPEG or TIFF")


def _pixel_size_m(crs: CRS, transform: Affine, width: int, height: int) -> float:
    if crs.is_projected:
        unit = (crs.axis_info[0].unit_conversion_factor or 1.0)
        return float(abs(transform.a) * unit)
    # geographic CRS: measure the geodesic length of one pixel at the raster centre
    from pyproj import Geod
    cx, cy = transform @ (width / 2, height / 2)
    nx, _ = transform @ (width / 2 + 1, height / 2)
    _, az = None, None
    g = Geod(ellps="WGS84")
    _, _, d = g.inv(cx, cy, nx, cy)
    return float(d)


def inspect_raster(path: Path) -> RasterInfo:
    kind = sniff_type(path)
    if kind == "tiff":
        try:
            with rasterio.open(path) as ds:
                if ds.count < 3:
                    raise RasterError(f"Need at least 3 bands (RGB); file has {ds.count}")
                info = RasterInfo(ds.width, ds.height, ds.count, False)
                if ds.crs is not None and not ds.transform.is_identity:
                    crs = CRS.from_user_input(ds.crs)
                    info.georeferenced = True
                    info.crs = crs.to_string()
                    info.transform = list(ds.transform)[:6]
                    b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
                    info.bounds_wgs84 = [float(v) for v in b]
                    info.pixel_size_m = _pixel_size_m(crs, ds.transform, ds.width, ds.height)
                info.meta = {"dtype": ds.dtypes[0], "nodata": ds.nodata, "driver": ds.driver}
                return info
        except rasterio.errors.RasterioError as e:
            raise RasterError(f"Unreadable raster: {e}") from e
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RasterError("Unreadable image")
    h, w = img.shape[:2]
    if min(h, w) < 64:
        raise RasterError(f"Image too small ({w}x{h}); minimum 64x64")
    return RasterInfo(w, h, 1 if img.ndim == 2 else img.shape[2], False, meta={"dtype": str(img.dtype)})


def read_rgb(path: Path, bands: tuple[int, int, int] = (1, 2, 3)) -> np.ndarray:
    """Return HxWx3 uint8. 16-bit/float data is percentile-stretched (2-98%) per band."""
    kind = sniff_type(path)
    if kind == "tiff":
        with rasterio.open(path) as ds:
            arr = ds.read(list(bands)).astype(np.float32)
            nodata = ds.nodata
        arr = arr.transpose(1, 2, 0)
        if nodata is not None:
            arr = np.where(arr == nodata, 0, arr)
        if arr.max() > 255 or arr.min() < 0 or (arr.max() <= 1.0 and arr.max() > 0):
            out = np.zeros_like(arr, dtype=np.uint8)
            for c in range(3):
                v = arr[..., c]; valid = v[v > 0] if (v > 0).any() else v.ravel()
                lo, hi = np.percentile(valid, [2, 98]); hi = hi if hi > lo else lo + 1
                out[..., c] = np.clip((v - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
            return out
        return arr.astype(np.uint8)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RasterError("Unreadable image")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def affine_of(obs) -> Affine | None:
    return Affine(*obs.transform) if obs.transform else None


def check_alignment(b, a) -> dict:
    """Assess whether two observations can be compared. `b`,`a` are Observation rows (before/after)."""
    notes: list[str] = []
    status = "ok"
    out: dict = {"mode": "pixel", "same_size": (b.width, b.height) == (a.width, a.height)}
    if b.georeferenced and a.georeferenced:
        out["mode"] = "georeferenced"
        bb, ab = b.bounds_wgs84, a.bounds_wgs84
        ix0, iy0, ix1, iy1 = max(bb[0], ab[0]), max(bb[1], ab[1]), min(bb[2], ab[2]), min(bb[3], ab[3])
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        ua = (bb[2] - bb[0]) * (bb[3] - bb[1]); ub = (ab[2] - ab[0]) * (ab[3] - ab[1])
        overlap = inter / max(min(ua, ub), 1e-12)
        out["overlap_fraction"] = round(overlap, 4)
        if overlap < 0.5:
            status = "unsuitable"; notes.append(f"Footprints overlap only {overlap:.0%}; not a comparable pair.")
        elif overlap < 0.9:
            status = "warning"; notes.append(f"Footprints overlap {overlap:.0%}; only the overlapping area is analysed.")
        if b.crs != a.crs or b.transform != a.transform or not out["same_size"]:
            notes.append("After-image is reprojected/resampled onto the before-image grid.")
        out["resample_required"] = not (b.crs == a.crs and b.transform == a.transform and out["same_size"])
    elif b.georeferenced != a.georeferenced:
        status = "unsuitable"
        notes.append("One observation is georeferenced and the other is not; spatial alignment cannot be verified.")
    else:
        if not out["same_size"]:
            status = "unsuitable"
            notes.append(f"Image sizes differ ({b.width}x{b.height} vs {a.width}x{a.height}) and no georeferencing is "
                         "available to align them. Not silently resized.")
        else:
            notes.append("No georeferencing: alignment assumed by identical pixel grid only (verified by phase correlation).")
    out["status"] = status
    out["notes"] = notes
    return out


def load_aligned_pair(b, a) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return (before_rgb, after_rgb_on_before_grid, info) where the arrays share a pixel grid."""
    before = read_rgb(Path(b.file_path))
    info: dict = {}
    if b.georeferenced and a.georeferenced and (b.crs != a.crs or b.transform != a.transform or (b.width, b.height) != (a.width, a.height)):
        after_src = read_rgb(Path(a.file_path))
        dst = np.zeros_like(before)
        with rasterio.open(a.file_path) as ds:
            for c in range(3):
                reproject(source=after_src[..., c], destination=dst[..., c], src_transform=ds.transform, src_crs=ds.crs,
                          dst_transform=affine_of(b), dst_crs=CRS.from_string(b.crs), resampling=Resampling.bilinear)
        after = dst
        info["reprojected"] = True
        info["valid_fraction_after"] = float((after.sum(2) > 0).mean())
    else:
        after = read_rgb(Path(a.file_path))
    return before, after, info


def registration_shift(before: np.ndarray, after: np.ndarray) -> tuple[float, float, float]:
    """Phase-correlation estimate of global translation between dates (pixels) and its response."""
    g1 = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g2 = cv2.cvtColor(after, cv2.COLOR_RGB2GRAY).astype(np.float32)
    win = cv2.createHanningWindow(g1.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(g1, g2, win)
    return float(dx), float(dy), float(resp)


def domain_compatibility(pixel_size_m: float | None) -> dict:
    """The model is trained on LEVIR-CD (0.5 m aerial/satellite RGB). Report how far an input is from that domain."""
    if pixel_size_m is None:
        return {"status": "unknown", "gsd_m": None, "levir_gsd_m": LEVIR_GSD_M,
                "notes": ["No georeferencing: ground sampling distance unknown; domain match to LEVIR-CD cannot be assessed."]}
    ratio = pixel_size_m / LEVIR_GSD_M
    if ratio <= 2:
        st, note = "compatible", "Ground sampling distance is close to the training domain (0.5 m)."
    elif ratio <= 6:
        st, note = "warning", "Coarser than the training domain; building-scale changes may be missed or distorted."
    else:
        st, note = "unvalidated", ("Ground sampling distance is much coarser than LEVIR-CD (0.5 m). The model has NOT been "
                                  "validated for this resolution; results are exploratory and not performance-validated.")
    return {"status": st, "gsd_m": round(pixel_size_m, 3), "levir_gsd_m": LEVIR_GSD_M, "scale_ratio": round(ratio, 2), "notes": [note]}
