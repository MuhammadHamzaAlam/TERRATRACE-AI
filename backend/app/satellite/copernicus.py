"""Copernicus Data Space Ecosystem (CDSE) Sentinel-2 L2A client.

Catalogue search (OData) needs no credentials. Downloads need a free CDSE account: CDSE_USERNAME / CDSE_PASSWORD env vars.
To avoid ~1 GB zips we download only the 10 m true-colour image (TCI) and 20 m scene-classification (SCL) bands via the
OData Nodes API, crop to the AOI, mask clouds/shadows and write a georeferenced GeoTIFF.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from app.core.config import get_settings

CATALOGUE = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
# SCL classes treated as unusable: 0 no data, 1 saturated, 3 cloud shadow, 8/9 cloud medium/high, 10 thin cirrus, 11 snow
SCL_MASK = (0, 1, 3, 8, 9, 10, 11)


class SatelliteError(RuntimeError):
    pass


def credentials_configured() -> bool:
    s = get_settings()
    return bool(s.cdse_username and s.cdse_password)


def integration_status() -> dict:
    return {"search_available": True, "download_available": credentials_configured(),
            "message": None if credentials_configured() else
            "Scene search works without credentials. Set CDSE_USERNAME and CDSE_PASSWORD (free account at "
            "https://dataspace.copernicus.eu/) to enable downloads."}


def _wkt_polygon(bbox: list[float]) -> str:
    x0, y0, x1, y1 = bbox
    return f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"


def _attr(p: dict, name: str):
    for a in p.get("Attributes", []):
        if a.get("Name") == name:
            return a.get("Value")
    return None


def search_scenes(bbox: list[float], start: str, end: str, max_cloud: float = 30.0, top: int = 20,
                  client: httpx.Client | None = None) -> list[dict]:
    x0, y0, x1, y1 = bbox
    if not (-180 <= x0 < x1 <= 180 and -90 <= y0 < y1 <= 90):
        raise SatelliteError("bbox must be [minLon, minLat, maxLon, maxLat] in EPSG:4326")
    flt = (f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'SRID=4326;{_wkt_polygon(bbox)}') "
           f"and ContentDate/Start gt {start}T00:00:00.000Z and ContentDate/Start lt {end}T23:59:59.999Z "
           "and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') "
           f"and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {float(max_cloud)})")
    params = {"$filter": flt, "$top": str(min(top, 100)), "$expand": "Attributes", "$orderby": "ContentDate/Start desc"}
    c = client or httpx.Client(timeout=40)
    try:
        r = c.get(f"{CATALOGUE}/Products", params=params)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise SatelliteError(f"Copernicus catalogue unavailable: {e}") from e
    finally:
        if client is None: c.close()
    out = []
    for p in r.json().get("value", []):
        out.append({"id": p["Id"], "name": p["Name"], "acquisition_date": p["ContentDate"]["Start"][:10],
                    "acquisition_datetime": p["ContentDate"]["Start"], "cloud_cover": _attr(p, "cloudCover"),
                    "tile_id": _attr(p, "tileId"), "size_mb": round(p.get("ContentLength", 0) / 1e6, 1),
                    "footprint": p.get("GeoFootprint"), "online": p.get("Online", True), "product_type": "S2MSI2A",
                    "preview_url": f"/api/satellite/scenes/{p['Id']}/quicklook"})
    return out


def get_token(client: httpx.Client) -> str:
    s = get_settings()
    if not credentials_configured():
        raise SatelliteError("CDSE credentials not configured (CDSE_USERNAME / CDSE_PASSWORD)")
    r = client.post(TOKEN_URL, data={"grant_type": "password", "client_id": s.cdse_client_id,
                                     "username": s.cdse_username, "password": s.cdse_password})
    if r.status_code != 200:
        raise SatelliteError(f"CDSE authentication failed (HTTP {r.status_code})")  # never echo credentials/body
    return r.json()["access_token"]


def quicklook(product_id: str, client: httpx.Client | None = None) -> bytes:
    c = client or httpx.Client(timeout=40, follow_redirects=True)
    try:
        r = c.get(f"{CATALOGUE}/Products({product_id})", params={"$expand": "Assets"})
        r.raise_for_status()
        for a in r.json().get("Assets", []):
            if a.get("Type") == "QUICKLOOK":
                img = c.get(a["DownloadLink"]); img.raise_for_status(); return img.content
    except httpx.HTTPError as e:
        raise SatelliteError(f"Quicklook unavailable: {e}") from e
    finally:
        if client is None: c.close()
    raise SatelliteError("No quicklook asset for this product")


def _children(c: httpx.Client, token: str, base: str) -> list[dict]:
    r = c.get(f"{base}/Nodes", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise SatelliteError(f"Node listing failed (HTTP {r.status_code})")
    return r.json().get("result", [])


def _find_band_urls(c: httpx.Client, token: str, product_id: str, product_name: str) -> dict[str, str]:
    base = f"{DOWNLOAD}/Products({product_id})/Nodes({product_name})"
    gran = _children(c, token, f"{base}/Nodes(GRANULE)")
    if not gran: raise SatelliteError("No GRANULE directory in product")
    gbase = f"{base}/Nodes(GRANULE)/Nodes({gran[0]['Name']})/Nodes(IMG_DATA)"
    urls = {}
    for res, key, suffix in (("R10m", "tci", "_TCI_10m.jp2"), ("R20m", "scl", "_SCL_20m.jp2")):
        for n in _children(c, token, f"{gbase}/Nodes({res})"):
            if n["Name"].endswith(suffix):
                urls[key] = f"{gbase}/Nodes({res})/Nodes({n['Name']})/$value"
    if "tci" not in urls:
        raise SatelliteError("TCI_10m band not found in product")
    return urls


def _download(c: httpx.Client, token: str, url: str, dest: Path) -> None:
    with c.stream("GET", url, headers={"Authorization": f"Bearer {token}"}, follow_redirects=True) as r:
        if r.status_code != 200:
            raise SatelliteError(f"Download failed (HTTP {r.status_code})")
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1 << 20): f.write(chunk)


def process_scene(tci_path: Path, scl_path: Path | None, bbox_wgs84: list[float], out_path: Path, max_cloud_frac: float = 0.4) -> dict:
    """Crop TCI to bbox, mask SCL cloud/shadow/snow/nodata (set to 0 = nodata), write RGB GeoTIFF. Returns processing report."""
    with rasterio.open(tci_path) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox_wgs84, densify_pts=21)
        win = from_bounds(*b, transform=ds.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
        if win.width < 16 or win.height < 16:
            raise SatelliteError("AOI does not intersect this scene (or is too small)")
        rgb = ds.read([1, 2, 3], window=win)
        tf = ds.window_transform(win); crs = ds.crs
    mask = np.zeros(rgb.shape[1:], bool)
    if scl_path:
        # Resample SCL (20 m) onto the TCI crop grid exactly via warp
        from rasterio.warp import reproject
        scl_on = np.zeros(rgb.shape[1:], np.uint8)
        with rasterio.open(scl_path) as sc:
            reproject(rasterio.band(sc, 1), scl_on, dst_transform=tf, dst_crs=crs, resampling=Resampling.nearest)
        mask = np.isin(scl_on, SCL_MASK)
    cloud_frac = float(mask.mean())
    rgb = rgb.copy(); rgb[:, mask] = 0
    with rasterio.open(out_path, "w", driver="GTiff", height=rgb.shape[1], width=rgb.shape[2], count=3, dtype="uint8",
                       crs=crs, transform=tf, nodata=0, compress="deflate") as dst:
        dst.write(rgb)
    return {"cloud_masked_fraction": round(cloud_frac, 4), "usable": cloud_frac <= max_cloud_frac,
            "size": [rgb.shape[2], rgb.shape[1]], "bands": "TCI (B04,B03,B02 true colour, 10 m)", "masked_classes": list(SCL_MASK)}


def download_and_prepare(product: dict, bbox_wgs84: list[float], work_dir: Path, out_path: Path, update=lambda p, m: None) -> dict:
    """product: {'id','name'} from search_scenes. Requires credentials."""
    work_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(120, connect=20)) as c:
        update(0.05, "Authenticating with Copernicus Data Space")
        token = get_token(c)
        update(0.1, "Locating bands")
        urls = _find_band_urls(c, token, product["id"], product["name"])
        tci, scl = work_dir / "tci.jp2", work_dir / "scl.jp2"
        update(0.2, "Downloading true-colour band (10 m)")
        _download(c, token, urls["tci"], tci)
        if "scl" in urls:
            update(0.7, "Downloading scene classification")
            _download(c, token, urls["scl"], scl)
    update(0.85, "Cropping and cloud-masking")
    rep = process_scene(tci, scl if scl.exists() else None, bbox_wgs84, out_path)
    for f in (tci, scl): f.unlink(missing_ok=True)
    return rep
