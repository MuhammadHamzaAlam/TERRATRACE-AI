"""End-to-end analysis pipeline: align -> infer -> extract events -> georeference -> cluster -> track -> prioritise -> persist."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import models as m
from app.database.session import SessionLocal
from app.geospatial import raster
from app.geospatial.clustering import cluster_events
from app.geospatial.events import GeoRef, extract_events
from app.monitoring.association import rebuild_tracks
from app.services import model_service

DEFAULT_CONFIG = {"threshold": 0.5, "min_event_pixels": 20, "cluster_eps": None, "cluster_min_samples": 2,
                  "allow_domain_gap": False, "allow_misaligned": False, "priority_weights": None}


def analysis_dir(analysis_id: str) -> Path:
    d = get_settings().storage_dir / "analyses" / analysis_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def preflight(db: Session, an: m.Analysis) -> dict:
    """Checks that do not require running the model. Returns {ok, alignment, compatibility, blockers}."""
    b, a = an.before_obs, an.after_obs
    cfg = {**DEFAULT_CONFIG, **(an.config or {})}
    blockers = []
    if a.acquisition_date <= b.acquisition_date:
        blockers.append("The 'after' observation must be later than the 'before' observation.")
    al = raster.check_alignment(b, a)
    if al["status"] == "unsuitable" and not cfg["allow_misaligned"]:
        blockers += al["notes"]
    comp = raster.domain_compatibility(b.pixel_size_m)
    if comp["status"] == "unvalidated" and not cfg["allow_domain_gap"]:
        blockers.append("Input resolution is far outside the LEVIR-CD training domain; set allow_domain_gap=true to run "
                        "an explicitly unvalidated exploratory analysis.")
    return {"ok": not blockers, "alignment": al, "compatibility": comp, "blockers": blockers}


def run_analysis(analysis_id: str, update) -> None:
    s = get_settings()
    with SessionLocal() as db:
        an = db.get(m.Analysis, analysis_id)
        try:
            _run(db, an, update, s)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            an = db.get(m.Analysis, analysis_id)
            an.status, an.status_message = ("blocked" if e.__class__.__name__ == "ModelUnavailable" else "failed"), str(e)[:1000]
            db.commit()
            raise


def _run(db: Session, an: m.Analysis, update, s) -> None:
    cfg = {**DEFAULT_CONFIG, **(an.config or {})}
    an.status, an.progress, an.status_message = "running", 0.02, "Validating inputs"
    db.commit()
    pf = preflight(db, an)
    an.alignment, an.compatibility = pf["alignment"], pf["compatibility"]
    if not pf["ok"]:
        an.status, an.status_message = "blocked", " ".join(pf["blockers"])
        db.commit(); return
    pred = model_service.get_predictor()  # raises ModelUnavailable (-> status 'blocked') if no checkpoint
    mv = model_service.sync_registry(db)
    an.model_version_id = mv.id if mv else None
    b, a = an.before_obs, an.after_obs
    update(0.05, "Loading and aligning images")
    before, after, info = raster.load_aligned_pair(b, a)
    if before.shape != after.shape:
        raise ValueError(f"Aligned images differ in shape {before.shape} vs {after.shape}")
    dx, dy, resp = raster.registration_shift(before, after)
    an.alignment = {**an.alignment, "global_shift_px": [round(dx, 2), round(dy, 2)], "phase_correlation_response": round(resp, 4), **info}
    if max(abs(dx), abs(dy)) > 8 and not cfg["allow_misaligned"]:
        an.alignment["status"] = "warning"
        an.alignment["notes"] = an.alignment.get("notes", []) + [
            f"Estimated global shift between dates is ({dx:.1f}, {dy:.1f}) px; misregistration may create false detections."]
    db.commit()

    def prog(f: float):
        update(0.1 + 0.6 * f, "Running Siamese U-Net inference")
        an.progress = 0.1 + 0.6 * f

    prob = pred.predict_proba(before, after, tile=s.tile_size, overlap=s.tile_overlap, progress=prog)
    d = analysis_dir(an.id)
    cv2.imwrite(str(d / "prob.png"), (prob * 65535).astype(np.uint16))
    update(0.72, "Extracting candidate events")
    georef = GeoRef(b.crs, b.transform) if b.georeferenced else None
    raw, mask = extract_events(prob, cfg["threshold"], cfg["min_event_pixels"], georef)
    cv2.imwrite(str(d / "mask.png"), mask * 255)
    overlay = before.copy()
    red = np.zeros_like(overlay); red[..., 0] = 255
    overlay = np.where(mask[..., None] > 0, (0.55 * overlay + 0.45 * red).astype(np.uint8), overlay)
    cv2.imwrite(str(d / "overlay.jpg"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    an.mask_path, an.prob_path, an.overlay_path = str(d / "mask.png"), str(d / "prob.png"), str(d / "overlay.jpg")

    update(0.8, "Clustering and persisting events")
    db.query(m.Event).filter(m.Event.analysis_id == an.id).delete()
    db.query(m.Cluster).filter(m.Cluster.analysis_id == an.id).delete()
    db.flush()
    ev_dicts = [dict(centroid_px=e.centroid_px, centroid_geo=e.centroid_geo, area_px=e.area_px, area_m2=e.area_m2, conf_mean=e.conf_mean) for e in raw]
    eps = cfg["cluster_eps"] or (50.0 if georef else 64.0)
    cl = cluster_events(ev_dicts, eps=eps, min_samples=cfg["cluster_min_samples"])
    cl_ids = []
    for i, c in enumerate(cl["clusters"]):
        row = m.Cluster(id=f"{an.id}:CL-{i + 1:03d}", label=f"CL-{i + 1:03d}", analysis_id=an.id, event_count=c["event_count"],
                        total_area_px=c["total_area_px"], total_area_m2=c["total_area_m2"], centroid_px=c["centroid_px"],
                        centroid_geo=c["centroid_geo"], extent_px=c["extent_px"], boundary_geo=c["boundary_geo"],
                        mean_confidence=c["mean_confidence"], params={"eps": eps, "unit": cl["unit"], "min_samples": cfg["cluster_min_samples"]})
        db.add(row); cl_ids.append(row.id)
    for i, e in enumerate(raw):
        lab = cl["labels"][i]
        db.add(m.Event(id=f"{an.id}:EVT-{e.index:03d}", label=f"EVT-{e.index:03d}", analysis_id=an.id, project_id=an.project_id,
                       cluster_id=cl_ids[lab] if lab >= 0 else None, bbox_px=e.bbox_px, centroid_px=e.centroid_px,
                       area_px=e.area_px, area_m2=e.area_m2, area_pct=e.area_pct, conf_mean=e.conf_mean, conf_max=e.conf_max,
                       conf_min=e.conf_min, geometry_geo=e.geometry_geo, centroid_geo=e.centroid_geo,
                       before_date=b.acquisition_date, after_date=a.acquisition_date))
    h, w = mask.shape
    total_px = float(mask.sum())
    an.metrics = {
        "n_events": len(raw), "n_clusters": len(cl["clusters"]), "image_size": [w, h],
        "changed_pixels": total_px, "changed_pct": 100.0 * total_px / (w * h),
        "changed_area_m2": float(sum(e.area_m2 for e in raw)) if georef else None,
        "mean_confidence": float(np.mean([e.conf_mean for e in raw])) if raw else None,
        "georeferenced": bool(georef), "cluster_unit": cl["unit"],
    }
    an.status, an.progress, an.status_message, an.completed_at = "completed", 1.0, "Completed", datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    update(0.92, "Associating events across observations")
    rebuild_tracks(db, an.project_id)


def make_thumbnail(src: Path, dst: Path, max_side: int = 1600) -> None:
    img = raster.read_rgb(src)
    h, w = img.shape[:2]
    sc = min(1.0, max_side / max(h, w))
    if sc < 1.0:
        img = cv2.resize(img, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(dst), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
