from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404, get_event_or_404, get_project_or_404, reviewer_name
from app.database import models as m
from app.database.session import get_db
from app.jobs import runner
from app.review import service as review
from app.schemas.api import AnalysisIn, BulkReviewIn, ReviewIn
from app.services import pipeline, queries

router = APIRouter(tags=["analyses"])


def analysis_dict(a: m.Analysis, db: Session) -> dict:
    return {"id": a.id, "project_id": a.project_id, "status": a.status, "progress": a.progress, "status_message": a.status_message,
            "before_observation_id": a.before_obs_id, "after_observation_id": a.after_obs_id,
            "before_date": a.before_obs.acquisition_date.isoformat(), "after_date": a.after_obs.acquisition_date.isoformat(),
            "georeferenced": a.before_obs.georeferenced, "image_size": [a.before_obs.width, a.before_obs.height],
            "model_version_id": a.model_version_id, "config": a.config, "alignment": a.alignment, "compatibility": a.compatibility,
            "metrics": a.metrics, "has_mask": bool(a.mask_path), "created_at": a.created_at.isoformat(),
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "note": "Predictions are model output (not ground truth)."}


@router.post("/projects/{project_id}/analyses", status_code=201)
def create_analysis(body: AnalysisIn, p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    b = db.get(m.Observation, body.before_observation_id); a = db.get(m.Observation, body.after_observation_id)
    if not b or not a or b.project_id != p.id or a.project_id != p.id:
        raise HTTPException(404, "Both observations must belong to this project")
    if b.id == a.id: raise HTTPException(422, "Choose two different observations")
    cfg = body.model_dump(exclude={"before_observation_id", "after_observation_id", "start"})
    an = m.Analysis(project_id=p.id, before_obs_id=b.id, after_obs_id=a.id, config=cfg)
    db.add(an); db.commit(); db.refresh(an)
    job_id = None
    if body.start:
        job_id = runner.submit("analysis", an.id, lambda upd, _id=an.id: pipeline.run_analysis(_id, upd))
    return {**analysis_dict(an, db), "job_id": job_id}


@router.post("/analyses/{analysis_id}/start")
def start_analysis(analysis_id: str, db: Session = Depends(get_db)):
    an = get_analysis_or_404(db, analysis_id)
    if an.status == "running": raise HTTPException(409, "Analysis already running")
    an.status, an.progress, an.status_message = "pending", 0.0, ""; db.commit()
    return {"job_id": runner.submit("analysis", an.id, lambda upd, _id=an.id: pipeline.run_analysis(_id, upd))}


@router.get("/projects/{project_id}/analyses")
def list_analyses(p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return [analysis_dict(a, db) for a in sorted(p.analyses, key=lambda a: a.created_at, reverse=True)]


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    return analysis_dict(get_analysis_or_404(db, analysis_id), db)


@router.get("/analyses/{analysis_id}/status")
def analysis_status(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id)
    return {"id": a.id, "status": a.status, "progress": a.progress, "message": a.status_message}


@router.get("/analyses/{analysis_id}/summary")
def get_summary(analysis_id: str, db: Session = Depends(get_db)):
    return queries.analysis_summary(db, get_analysis_or_404(db, analysis_id))


@router.get("/analyses/{analysis_id}/preflight")
def preflight(analysis_id: str, db: Session = Depends(get_db)):
    return pipeline.preflight(db, get_analysis_or_404(db, analysis_id))


@router.get("/analyses/{analysis_id}/image/{kind}")
def analysis_image(analysis_id: str, kind: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id)
    path = {"before": a.before_obs.preview_path, "after": a.after_obs.preview_path, "mask": a.mask_path, "overlay": a.overlay_path}.get(kind)
    if kind not in ("before", "after", "mask", "overlay") or not path or not Path(path).exists():
        raise HTTPException(404, f"Image '{kind}' not available")
    return FileResponse(path)


@router.get("/analyses/{analysis_id}/compare/{other_id}")
def compare(analysis_id: str, other_id: str, db: Session = Depends(get_db)):
    a, b = get_analysis_or_404(db, analysis_id), get_analysis_or_404(db, other_id)
    if a.project_id != b.project_id: raise HTTPException(422, "Analyses belong to different projects")
    return queries.compare_analyses(db, a, b)


# ---------- events / clusters ----------
@router.get("/projects/{project_id}/events")
def list_events(project_id: str, analysis_id: str | None = None, confidence_min: float | None = None, confidence_max: float | None = None,
                review_status: str | None = None, cluster: str | None = None, priority_min: float | None = None,
                temporal_status: str | None = None, sort: str = "priority", order: str = "desc", limit: int = 200, offset: int = 0,
                bbox: str | None = None, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    bb = [float(x) for x in bbox.split(",")] if bbox else None
    if bb is not None and len(bb) != 4: raise HTTPException(422, "bbox must be minx,miny,maxx,maxy")
    rows, total = queries.query_events(db, project_id, analysis_id, confidence_min=confidence_min, confidence_max=confidence_max,
                                       review_status=review_status, cluster=cluster, priority_min=priority_min, sort=sort, order=order,
                                       limit=min(limit, 1000), offset=offset, temporal_status=temporal_status, bbox_wgs84=bb)
    return {"total": total, "events": [queries.event_dict(e) for e in rows]}


@router.get("/events/{event_uid}")
def get_event(event_uid: str, db: Session = Depends(get_db)):
    e = get_event_or_404(db, event_uid)
    d = queries.event_dict(e, detail=True)
    d["history"] = [history_dict(h) for h in e.history]
    track = db.get(m.EventTrack, e.track_id) if e.track_id else None
    if track:
        sib = db.query(m.Event).filter(m.Event.track_id == track.id).order_by(m.Event.after_date).all()
        d["track"] = {"id": track.id, "first_observed": track.first_observed.isoformat(), "last_observed": track.last_observed.isoformat(),
                      "n_observations": track.n_observations,
                      "observations": [{"event_id": s.label, "uid": s.id, "analysis_id": s.analysis_id, "after_date": s.after_date.isoformat(),
                                        "confidence": round(s.conf_mean, 4), "review_status": s.review_status} for s in sib]}
    return d


@router.get("/events/{event_uid}/crop/{kind}")
def event_crop(event_uid: str, kind: str, pad: int = 24, db: Session = Depends(get_db)):
    import cv2, numpy as np
    from fastapi.responses import Response
    from app.geospatial import raster
    e = get_event_or_404(db, event_uid); an = e.analysis
    if kind not in ("before", "after", "mask"): raise HTTPException(404, "kind must be before|after|mask")
    x0, y0, x1, y1 = e.bbox_px
    if kind == "mask":
        if not an.mask_path: raise HTTPException(404, "No mask")
        img = cv2.cvtColor(cv2.imread(an.mask_path, cv2.IMREAD_GRAYSCALE), cv2.COLOR_GRAY2RGB)
    else:
        before, after, _ = raster.load_aligned_pair(an.before_obs, an.after_obs)
        img = before if kind == "before" else after
    H, W = img.shape[:2]
    p = max(0, min(pad, 200))
    cx0, cy0, cx1, cy1 = max(0, x0 - p), max(0, y0 - p), min(W, x1 + p), min(H, y1 + p)
    crop = img[cy0:cy1, cx0:cx1].copy()
    cv2.rectangle(crop, (x0 - cx0, y0 - cy0), (x1 - cx0 - 1, y1 - cy0 - 1), (255, 200, 0), 1)
    scale = max(1, int(256 / max(crop.shape[:2])))
    if scale > 1: crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST if kind == "mask" else cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    return Response(buf.tobytes(), media_type="image/png")


@router.get("/projects/{project_id}/clusters")
def list_clusters(project_id: str, analysis_id: str | None = None, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    q = db.query(m.Cluster).join(m.Analysis).filter(m.Analysis.project_id == project_id)
    if analysis_id: q = q.filter(m.Cluster.analysis_id == analysis_id)
    return [queries.cluster_dict(c) for c in q.all()]


@router.get("/clusters/{cluster_uid}")
def get_cluster(cluster_uid: str, db: Session = Depends(get_db)):
    c = db.get(m.Cluster, cluster_uid)
    if not c: raise HTTPException(404, "Cluster not found")
    evs = db.query(m.Event).filter_by(cluster_id=c.id).all()
    return {**queries.cluster_dict(c), "events": [queries.event_dict(e) for e in evs],
            "distribution": {"mean_priority": c.priority_score, "min_conf": min((e.conf_min for e in evs), default=None),
                             "max_conf": max((e.conf_max for e in evs), default=None)}}


@router.get("/analyses/{analysis_id}/geojson")
def analysis_geojson(analysis_id: str, db: Session = Depends(get_db)):
    from app.reporting.exports import events_geojson
    a = get_analysis_or_404(db, analysis_id)
    if not a.before_obs.georeferenced:
        raise HTTPException(409, "GeoJSON unavailable: this analysis is not georeferenced (image-relative coordinates only)")
    return events_geojson(db, a.id)


# ---------- review ----------
def history_dict(h: m.EventHistory) -> dict:
    return {"id": h.id, "event_uid": h.event_id, "previous_status": h.previous_status, "new_status": h.new_status,
            "reviewer": h.reviewer, "notes": h.notes, "created_at": h.created_at.isoformat()}


@router.post("/events/{event_uid}/review")
def review_event(event_uid: str, body: ReviewIn, db: Session = Depends(get_db), reviewer: str = Depends(reviewer_name)):
    e = get_event_or_404(db, event_uid)
    try:
        rec = review.set_status(db, e, body.status, reviewer, body.notes)
    except review.ReviewError as ex:
        raise HTTPException(422, str(ex))
    return {"event": queries.event_dict(e), "record": history_dict(rec)}


@router.post("/projects/{project_id}/events/bulk-review")
def bulk_review(project_id: str, body: BulkReviewIn, db: Session = Depends(get_db), reviewer: str = Depends(reviewer_name)):
    get_project_or_404(project_id, db)
    try:
        n = review.bulk_set_status(db, body.event_ids, body.status, reviewer, body.notes, body.confirm, project_id)
    except review.ReviewError as ex:
        raise HTTPException(422, str(ex))
    return {"updated": n}


@router.get("/projects/{project_id}/review-history")
def review_history(project_id: str, limit: int = 200, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    rows = (db.query(m.EventHistory, m.Event).join(m.Event, m.Event.id == m.EventHistory.event_id)
            .filter(m.Event.project_id == project_id).order_by(m.EventHistory.id.desc()).limit(min(limit, 1000)).all())
    return [{**history_dict(h), "event_id": e.label, "analysis_id": e.analysis_id} for h, e in rows]
