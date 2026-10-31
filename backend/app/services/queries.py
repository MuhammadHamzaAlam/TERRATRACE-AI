"""Shared read-side queries used by both the REST API and the LLM tool layer (single source of truth for numbers)."""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import models as m


def event_dict(e: m.Event, detail: bool = False) -> dict:
    d = {
        "event_id": e.label, "uid": e.id, "analysis_id": e.analysis_id, "project_id": e.project_id, "cluster": e.cluster_id.split(":")[-1] if e.cluster_id else None,
        "area_px": e.area_px, "area_m2": e.area_m2, "area_pct": round(e.area_pct, 4),
        "confidence": round(e.conf_mean, 4), "priority_score": e.priority_score, "review_status": e.review_status,
        "temporal_status": e.temporal_status, "track_id": e.track_id, "centroid_px": e.centroid_px, "centroid_geo": e.centroid_geo,
        "bbox_px": e.bbox_px, "before_date": e.before_date.isoformat(), "after_date": e.after_date.isoformat(),
        "label": "candidate change event",
    }
    if detail:
        d.update(conf_max=e.conf_max, conf_min=e.conf_min, geometry_geo=e.geometry_geo, priority_factors=e.priority_factors)
    return d


def query_events(db: Session, project_id: str, analysis_id: str | None = None, *, confidence_min: float | None = None,
                 confidence_max: float | None = None, review_status: str | None = None, cluster: str | None = None,
                 priority_min: float | None = None, min_area_px: float | None = None, sort: str = "priority",
                 order: str = "desc", limit: int = 100, offset: int = 0, temporal_status: str | None = None,
                 bbox_wgs84: list[float] | None = None, after_date_from=None, after_date_to=None) -> tuple[list[m.Event], int]:
    q = db.query(m.Event).filter(m.Event.project_id == project_id)
    if analysis_id: q = q.filter(m.Event.analysis_id == analysis_id)
    if confidence_min is not None: q = q.filter(m.Event.conf_mean >= confidence_min)
    if confidence_max is not None: q = q.filter(m.Event.conf_mean <= confidence_max)
    if review_status: q = q.filter(m.Event.review_status == review_status)
    if cluster: q = q.filter(m.Event.cluster_id.like(f"%:{cluster}"))
    if priority_min is not None: q = q.filter(m.Event.priority_score >= priority_min)
    if min_area_px is not None: q = q.filter(m.Event.area_px >= min_area_px)
    if temporal_status: q = q.filter(m.Event.temporal_status == temporal_status)
    if after_date_from: q = q.filter(m.Event.after_date >= after_date_from)
    if after_date_to: q = q.filter(m.Event.after_date <= after_date_to)
    cols = {"priority": m.Event.priority_score, "confidence": m.Event.conf_mean, "area": m.Event.area_px, "id": m.Event.id}
    col = cols.get(sort, m.Event.priority_score)
    q = q.order_by(col.desc() if order == "desc" else col.asc(), m.Event.id)
    rows = q.all()
    if bbox_wgs84:  # spatial filter in Python on real centroid_geo (portable to PostgreSQL w/o PostGIS)
        x0, y0, x1, y1 = bbox_wgs84
        rows = [e for e in rows if e.centroid_geo and x0 <= e.centroid_geo[0] <= x1 and y0 <= e.centroid_geo[1] <= y1]
    total = len(rows)
    return rows[offset:offset + limit], total


def analysis_summary(db: Session, an: m.Analysis) -> dict:
    evs = db.query(m.Event).filter(m.Event.analysis_id == an.id).all()
    by_status = {s: 0 for s in ("pending", "confirmed", "rejected", "needs_investigation")}
    for e in evs: by_status[e.review_status] = by_status.get(e.review_status, 0) + 1
    conf = [e.conf_mean for e in evs]
    bins = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
    hist = [{"range": f"{bins[i]:.1f}-{min(bins[i+1],1.0):.1f}", "count": sum(1 for c in conf if bins[i] <= c < bins[i + 1])} for i in range(5)]
    return {
        "analysis_id": an.id, "project_id": an.project_id, "status": an.status, "status_message": an.status_message,
        "before_date": an.before_obs.acquisition_date.isoformat(), "after_date": an.after_obs.acquisition_date.isoformat(),
        "before_observation": an.before_obs_id, "after_observation": an.after_obs_id,
        "n_events": len(evs), "n_clusters": (an.metrics or {}).get("n_clusters", 0),
        "changed_pct": (an.metrics or {}).get("changed_pct"), "changed_pixels": (an.metrics or {}).get("changed_pixels"),
        "changed_area_m2": (an.metrics or {}).get("changed_area_m2"), "georeferenced": (an.metrics or {}).get("georeferenced", False),
        "mean_confidence": (an.metrics or {}).get("mean_confidence"), "review_status_counts": by_status,
        "confidence_distribution": hist, "model_version_id": an.model_version_id,
        "alignment_status": (an.alignment or {}).get("status"), "domain_compatibility": (an.compatibility or {}).get("status"),
        "caveat": "Counts are model-predicted candidate change events, not confirmed real-world changes.",
    }


def cluster_dict(c: m.Cluster) -> dict:
    return {"cluster_id": c.label, "uid": c.id, "analysis_id": c.analysis_id, "event_count": c.event_count,
            "total_area_px": c.total_area_px, "total_area_m2": c.total_area_m2, "centroid_px": c.centroid_px,
            "centroid_geo": c.centroid_geo, "extent_px": c.extent_px, "boundary_geo": c.boundary_geo,
            "mean_confidence": round(c.mean_confidence, 4), "priority_score": c.priority_score, "params": c.params}


def compare_analyses(db: Session, a: m.Analysis, b: m.Analysis) -> dict:
    """Compare two completed analyses of the same project (a = reference/earlier, b = comparison)."""
    ea = db.query(m.Event).filter(m.Event.analysis_id == a.id).all()
    eb = db.query(m.Event).filter(m.Event.analysis_id == b.id).all()
    ta = {e.track_id for e in ea if e.track_id}; tb = {e.track_id for e in eb if e.track_id}
    sa, sb = analysis_summary(db, a), analysis_summary(db, b)

    def delta(x, y): return None if x is None or y is None else y - x
    by_track_b = {e.track_id: e for e in eb if e.track_id}
    return {
        "analysis_a": sa, "analysis_b": sb,
        "delta": {"n_events": sb["n_events"] - sa["n_events"], "changed_pct": delta(sa["changed_pct"], sb["changed_pct"]),
                  "changed_pixels": delta(sa["changed_pixels"], sb["changed_pixels"]),
                  "changed_area_m2": delta(sa["changed_area_m2"], sb["changed_area_m2"]), "n_clusters": sb["n_clusters"] - sa["n_clusters"]},
        "new_in_b": sorted(e.label for e in eb if e.track_id not in ta),
        "persisting": sorted(by_track_b[t].label for t in (ta & tb)),
        "not_detected_in_b": sorted(e.label for e in ea if e.track_id not in tb),
        "same_grid": (a.before_obs.width, a.before_obs.height) == (b.before_obs.width, b.before_obs.height),
        "caveat": "Differences describe changes in model detections between analyses, not confirmed real-world change.",
    }


def timeline(db: Session, project_id: str) -> dict:
    obs = db.query(m.Observation).filter(m.Observation.project_id == project_id).order_by(m.Observation.acquisition_date).all()
    ans = (db.query(m.Analysis).filter(m.Analysis.project_id == project_id, m.Analysis.status == "completed")
           .join(m.Observation, m.Analysis.after_obs_id == m.Observation.id).order_by(m.Observation.acquisition_date).all())
    tracks = db.query(m.EventTrack).filter(m.EventTrack.project_id == project_id).all()
    return {
        "observations": [{"id": o.id, "label": o.label, "date": o.acquisition_date.isoformat(), "source": o.source,
                          "georeferenced": o.georeferenced} for o in obs],
        "analyses": [{**{k: v for k, v in analysis_summary(db, a).items() if k in
                       ("analysis_id", "before_date", "after_date", "n_events", "n_clusters", "changed_pct", "changed_pixels", "changed_area_m2")}} for a in ans],
        "tracks": {"total": len(tracks), "recurring": sum(1 for t in tracks if t.n_observations > 1),
                   "single": sum(1 for t in tracks if t.n_observations == 1)},
        "note": "Trends are derived only from stored analyses; missing observation periods are not interpolated.",
    }
