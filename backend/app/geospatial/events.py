"""Pixel mask -> candidate change events, with optional georeferencing (Rasterio affine + PyProj + Shapely)."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from pyproj import CRS, Geod, Transformer
from rasterio.transform import Affine
from shapely.geometry import Polygon, mapping

_GEOD = Geod(ellps="WGS84")


@dataclass
class RawEvent:
    index: int
    bbox_px: list[int]
    centroid_px: list[float]
    area_px: float
    area_pct: float
    conf_mean: float
    conf_max: float
    conf_min: float
    polygon_px: list[list[float]]
    geometry_geo: dict | None = None
    centroid_geo: list[float] | None = None
    area_m2: float | None = None


class GeoRef:
    """Pixel <-> WGS84 conversion for one raster grid. Preserves CRS and affine transform."""

    def __init__(self, crs: str, transform: list[float]):
        self.crs = CRS.from_user_input(crs)
        self.affine = Affine(*transform)
        self.to_wgs = Transformer.from_crs(self.crs, CRS.from_epsg(4326), always_xy=True)
        self.from_wgs = Transformer.from_crs(CRS.from_epsg(4326), self.crs, always_xy=True)

    def px_to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        mx, my = self.affine @ (x, y)
        lon, lat = self.to_wgs.transform(mx, my)
        return float(lon), float(lat)

    def lonlat_to_px(self, lon: float, lat: float) -> tuple[float, float]:
        mx, my = self.from_wgs.transform(lon, lat)
        x, y = (~self.affine) @ (mx, my)
        return float(x), float(y)


def geodesic_area_m2(ring_lonlat: list[tuple[float, float]]) -> float:
    """Geodesic polygon area on the WGS84 ellipsoid (m^2) — correct regardless of the raster's CRS."""
    lons, lats = zip(*ring_lonlat)
    area, _ = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(float(area))


def extract_events(prob: np.ndarray, threshold: float = 0.5, min_pixels: int = 20,
                   georef: GeoRef | None = None, morph_open: int = 1) -> tuple[list[RawEvent], np.ndarray]:
    """Connected-component analysis (8-connectivity) of the thresholded probability map.
    Components are *candidate change events*, not confirmed buildings."""
    mask = (prob >= threshold).astype(np.uint8)
    if morph_open > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * morph_open + 1, 2 * morph_open + 1))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    total = mask.shape[0] * mask.shape[1]
    events: list[RawEvent] = []
    order = sorted(range(1, n), key=lambda i: (cents[i][1], cents[i][0]))  # deterministic top-to-bottom, left-to-right
    for i in order:
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_pixels:
            mask[labels == i] = 0
            continue
        x, y, w, h = (int(stats[i, c]) for c in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        comp = (labels[y:y + h, x:x + w] == i)
        vals = prob[y:y + h, x:x + w][comp]
        cnts, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cnts, key=cv2.contourArea)
        eps = max(0.5, 0.01 * cv2.arcLength(c, True))
        poly = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(float)
        if len(poly) < 3:  # degenerate: fall back to bbox rectangle
            poly = np.array([[0, 0], [w, 0], [w, h], [0, h]], float)
        # contour pixel centres -> pixel-edge polygon: expand by 0.5 px outward is negligible; use corners offset
        poly_px = [[float(px + x), float(py + y)] for px, py in poly]
        ev = RawEvent(len(events) + 1, [x, y, x + w, y + h], [float(cents[i][0]), float(cents[i][1])], float(area),
                      100.0 * area / total, float(vals.mean()), float(vals.max()), float(vals.min()), poly_px)
        if georef is not None:
            ring = [georef.px_to_lonlat(px, py) for px, py in poly_px]
            ring.append(ring[0])
            pg = Polygon(ring)
            if not pg.is_valid:
                pg = pg.buffer(0)
            ev.geometry_geo = mapping(pg)
            ev.centroid_geo = list(georef.px_to_lonlat(*ev.centroid_px))
            # area from pixel count * geodesic pixel area (exact component area, not simplified polygon area)
            px_area = _pixel_area_m2(georef, ev.centroid_px)
            ev.area_m2 = float(area * px_area)
        events.append(ev)
    return events, mask


def _pixel_area_m2(georef: GeoRef, centre: list[float]) -> float:
    x, y = centre
    ring = [georef.px_to_lonlat(x - 0.5, y - 0.5), georef.px_to_lonlat(x + 0.5, y - 0.5),
            georef.px_to_lonlat(x + 0.5, y + 0.5), georef.px_to_lonlat(x - 0.5, y + 0.5)]
    return geodesic_area_m2(ring)
