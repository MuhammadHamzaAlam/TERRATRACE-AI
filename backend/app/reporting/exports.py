from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from app.database import models as m


def events_geojson(db: Session, analysis_id: str) -> dict:
    evs = db.query(m.Event).filter(m.Event.analysis_id == analysis_id, m.Event.geometry_geo.isnot(None)).order_by(m.Event.id).all()
    return {"type": "FeatureCollection", "crs_note": "EPSG:4326 (WGS84)", "features": [
        {"type": "Feature", "id": e.label, "geometry": e.geometry_geo, "properties": {
            "event_id": e.label, "analysis_id": e.analysis_id, "cluster": e.cluster_id.split(":")[-1] if e.cluster_id else None,
            "confidence": round(e.conf_mean, 4), "area_m2": e.area_m2, "area_px": e.area_px, "priority_score": e.priority_score,
            "review_status": e.review_status, "temporal_status": e.temporal_status, "before_date": e.before_date.isoformat(),
            "after_date": e.after_date.isoformat(), "kind": "candidate change event (model prediction)"}} for e in evs]}


def events_csv(db: Session, analysis_id: str) -> str:
    evs = db.query(m.Event).filter(m.Event.analysis_id == analysis_id).order_by(m.Event.id).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["event_id", "analysis_id", "cluster", "confidence_mean", "confidence_max", "area_px", "area_m2", "area_pct",
                "priority_score", "review_status", "temporal_status", "centroid_x_px", "centroid_y_px", "lon", "lat",
                "before_date", "after_date"])
    for e in evs:
        w.writerow([e.label, e.analysis_id, e.cluster_id.split(":")[-1] if e.cluster_id else "", round(e.conf_mean, 4), round(e.conf_max, 4),
                    e.area_px, e.area_m2 if e.area_m2 is not None else "", round(e.area_pct, 4), e.priority_score, e.review_status,
                    e.temporal_status, round(e.centroid_px[0], 1), round(e.centroid_px[1], 1),
                    e.centroid_geo[0] if e.centroid_geo else "", e.centroid_geo[1] if e.centroid_geo else "",
                    e.before_date.isoformat(), e.after_date.isoformat()])
    return buf.getvalue()
