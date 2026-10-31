"""Temporal association of candidate events across analyses of one project.

Method (documented in docs/temporal-monitoring.md): analyses are processed in chronological order of their *after*
observation date. Each event is matched to an existing track (a recurring location) when
  (a) polygon IoU >= iou_min, or (b) centroid distance <= max(dist_m, equivalent radius of the larger event),
using geographic coordinates when both are georeferenced (metres in a local plane), otherwise image pixels —
pixel matching is only attempted between analyses whose images share the same pixel grid size.
Matching is greedy one-to-one per analysis (best IoU first, then nearest). Different event IDs do NOT imply different
physical structures; an event inherits the track of the location it overlaps.
"""
from __future__ import annotations

import math

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, shape
from sqlalchemy.orm import Session

from app.database import models as m
from app.geospatial.priority import score_event


def _local_transformer(lon0: float, lat0: float):
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m")
    return Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)


def _geom_local(ev: m.Event, tr) -> Polygon | None:
    if not ev.geometry_geo:
        return None
    g = shape(ev.geometry_geo)
    xs, ys = tr.transform(*zip(*g.exterior.coords))
    return Polygon(list(zip(xs, ys)))


def rebuild_tracks(db: Session, project_id: str, dist_m: float = 12.0, dist_px: float = 16.0, iou_min: float = 0.1) -> dict:
    analyses = (db.query(m.Analysis).filter(m.Analysis.project_id == project_id, m.Analysis.status == "completed")
                .join(m.Observation, m.Analysis.after_obs_id == m.Observation.id)
                .order_by(m.Observation.acquisition_date, m.Analysis.created_at).all())
    db.query(m.Event).filter(m.Event.project_id == project_id).update({m.Event.track_id: None})
    db.query(m.EventTrack).filter(m.EventTrack.project_id == project_id).delete()
    db.flush()
    tracks: list[dict] = []  # {obj, poly, centroid, geo(bool), grid(w,h), last_analysis}
    for an in analyses:
        evs = db.query(m.Event).filter(m.Event.analysis_id == an.id).order_by(m.Event.id).all()
        if not evs:
            continue
        geo = all(e.geometry_geo for e in evs)
        grid = (an.before_obs.width, an.before_obs.height)
        tr = None
        if geo:
            tr = _local_transformer(*np.mean([e.centroid_geo for e in evs], axis=0))
        used: set[str] = set()
        cands = []
        for e in evs:
            c = np.array(tr.transform(*e.centroid_geo)) if geo else np.array(e.centroid_px)
            poly = _geom_local(e, tr) if geo else Polygon([(a, b) for a, b in _px_poly(e)])
            for t in tracks:
                if t["geo"] != geo or (not geo and t["grid"] != grid) or t["last_analysis"] == an.id:
                    continue
                # tracks hold coordinates in the metric plane of when they were created -> recompute in this plane
                tc = np.array(tr.transform(*t["centroid_geo"])) if geo else np.array(t["centroid_px"])
                tp = _track_poly(t, tr, geo)
                d = float(np.linalg.norm(c - tc))
                inter = poly.intersection(tp).area if poly.is_valid and tp.is_valid else 0.0
                union = poly.union(tp).area if inter else 0.0
                iou = inter / union if union else 0.0
                rad = max(math.sqrt(poly.area / math.pi), math.sqrt(tp.area / math.pi))
                lim = max(dist_m if geo else dist_px, rad)
                if iou >= iou_min or d <= lim:
                    cands.append((-iou, d, e.id, id(t), t))
        cands.sort(key=lambda x: (x[0], x[1], x[2]))
        used_t: set[int] = set()
        assign: dict[str, dict] = {}
        for _, _, eid, tid, t in cands:
            if eid in assign or tid in used_t:
                continue
            assign[eid] = t; used_t.add(tid)
        for e in evs:
            t = assign.get(e.id)
            if t is None:
                obj = m.EventTrack(project_id=project_id, first_observed=e.after_date, last_observed=e.after_date,
                                   n_observations=0, centroid_px=e.centroid_px, centroid_geo=e.centroid_geo)
                db.add(obj); db.flush()
                t = {"obj": obj, "geo": geo, "grid": grid, "last_analysis": None}
                tracks.append(t)
                e.temporal_status = "new"
            else:
                e.temporal_status = "recurring"
            t["obj"].n_observations += 1
            t["obj"].last_observed = max(t["obj"].last_observed, e.after_date)
            t["obj"].first_observed = min(t["obj"].first_observed, e.after_date)
            t["obj"].centroid_px, t["obj"].centroid_geo = e.centroid_px, e.centroid_geo
            t["centroid_px"], t["centroid_geo"] = e.centroid_px, e.centroid_geo
            t["geometry_geo"], t["bbox_px"] = e.geometry_geo, e.bbox_px
            t["poly_px"] = _px_poly(e)
            t["last_analysis"] = an.id
            e.track_id = t["obj"].id
    db.commit()
    for an in analyses:
        rescore_analysis(db, an.id)
    return {"analyses": len(analyses), "tracks": len(tracks)}


def _px_poly(e: m.Event):
    x0, y0, x1, y1 = e.bbox_px
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _track_poly(t, tr, geo):
    if geo and t.get("geometry_geo"):
        return _geom_local_from_geojson(t["geometry_geo"], tr)
    if geo:
        return Polygon([(0, 0), (1, 0), (1, 1)])
    return Polygon(t["poly_px"])


def _geom_local_from_geojson(gj, tr):
    g = shape(gj)
    xs, ys = tr.transform(*zip(*g.exterior.coords))
    return Polygon(list(zip(xs, ys)))


def rescore_analysis(db: Session, analysis_id: str, weights: dict | None = None) -> None:
    an = db.get(m.Analysis, analysis_id)
    evs = db.query(m.Event).filter(m.Event.analysis_id == analysis_id).all()
    if not evs:
        return
    weights = weights or (an.config or {}).get("priority_weights")
    max_area = max(e.area_px for e in evs)
    clusters = {c.id: c for c in db.query(m.Cluster).filter(m.Cluster.analysis_id == analysis_id).all()}
    max_cl = max((c.event_count for c in clusters.values()), default=0)
    track_n = {t.id: t.n_observations for t in db.query(m.EventTrack).filter(m.EventTrack.project_id == an.project_id).all()}
    for e in evs:
        cs = clusters[e.cluster_id].event_count if e.cluster_id in clusters else 0
        r = score_event({"area_px": e.area_px, "conf_mean": e.conf_mean, "area_pct": e.area_pct}, max_area, cs, max_cl,
                        track_n.get(e.track_id, 1), weights)
        e.priority_score, e.priority_factors = r["score"], r
    for c in clusters.values():
        scores = [e.priority_score for e in evs if e.cluster_id == c.id]
        c.priority_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    db.commit()
