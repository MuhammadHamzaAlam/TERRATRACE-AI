"""Spatial clustering of candidate events (DBSCAN)."""
from __future__ import annotations

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import MultiPoint, Point, mapping
from sklearn.cluster import DBSCAN


def _local_metric_xy(lonlat: np.ndarray) -> np.ndarray:
    """Project lon/lat to a local azimuthal-equidistant plane (metres) centred on the data."""
    lon0, lat0 = float(lonlat[:, 0].mean()), float(lonlat[:, 1].mean())
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m")
    t = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
    x, y = t.transform(lonlat[:, 0], lonlat[:, 1])
    return np.column_stack([x, y])


def cluster_events(events: list[dict], eps: float, min_samples: int = 2, use_geo: bool = True) -> dict:
    """events: dicts with centroid_px, optional centroid_geo, area_px, area_m2, conf_mean.
    eps is in metres when georeferenced (use_geo and all events have centroid_geo), otherwise pixels."""
    if not events:
        return {"labels": [], "clusters": [], "unit": "px"}
    geo = use_geo and all(e.get("centroid_geo") for e in events)
    pts = _local_metric_xy(np.array([e["centroid_geo"] for e in events], float)) if geo else np.array([e["centroid_px"] for e in events], float)
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit(pts).labels_ if len(events) >= min_samples else np.full(len(events), -1)
    clusters = []
    for lab in sorted(set(labels) - {-1}):
        idx = [i for i, l in enumerate(labels) if l == lab]
        members = [events[i] for i in idx]
        cpx = np.mean([m["centroid_px"] for m in members], axis=0).tolist()
        pxs = np.array([m["centroid_px"] for m in members])
        c = {
            "members": idx, "event_count": len(idx), "total_area_px": float(sum(m["area_px"] for m in members)),
            "total_area_m2": float(sum(m["area_m2"] for m in members)) if geo and all(m.get("area_m2") is not None for m in members) else None,
            "centroid_px": cpx,
            "extent_px": [float(pxs[:, 0].min()), float(pxs[:, 1].min()), float(pxs[:, 0].max()), float(pxs[:, 1].max())],
            "mean_confidence": float(np.mean([m["conf_mean"] for m in members])),
            "centroid_geo": None, "boundary_geo": None,
        }
        if geo:
            ll = np.array([m["centroid_geo"] for m in members])
            c["centroid_geo"] = ll.mean(axis=0).tolist()
            hull = MultiPoint([tuple(p) for p in ll]).convex_hull
            if hull.geom_type != "Polygon":
                hull = hull.buffer(2e-5)  # ~2 m: make single/colinear point clusters drawable
            c["boundary_geo"] = mapping(hull)
        clusters.append(c)
    # stable ordering: largest event count first -> CL-001
    clusters.sort(key=lambda c: (-c["event_count"], -c["total_area_px"]))
    remap = {}
    for new, c in enumerate(clusters):
        for i in c["members"]:
            remap[i] = new
    return {"labels": [remap.get(i, -1) for i in range(len(events))], "clusters": clusters, "unit": "m" if geo else "px"}
