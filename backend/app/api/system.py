from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import models as m
from app.database.session import get_db
from app.llm import runtime
from app.satellite import copernicus as cdse
from app.services import model_service

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(m.Project.__table__.select().limit(1))
    return {"status": "ok", "database": "ok", "environment": get_settings().environment}


@router.get("/jobs/{job_id}")
def job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(m.Job, job_id)
    if not j: raise HTTPException(404, "Job not found")
    return {"id": j.id, "kind": j.kind, "ref_id": j.ref_id, "status": j.status, "progress": j.progress, "message": j.message}


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Everything here is read from the database; nothing is hardcoded."""
    q = db.query
    recent = q(m.Analysis).order_by(m.Analysis.created_at.desc()).limit(8).all()
    return {
        "counts": {"projects": q(m.Project).count(), "observations": q(m.Observation).count(),
                   "analyses_completed": q(m.Analysis).filter_by(status="completed").count(),
                   "analyses_total": q(m.Analysis).count(), "events": q(m.Event).count(),
                   "events_pending": q(m.Event).filter_by(review_status="pending").count(),
                   "events_confirmed": q(m.Event).filter_by(review_status="confirmed").count(),
                   "monitoring_regions": q(m.AOI).count(), "reports": q(m.Report).count()},
        "model": model_service.model_status(db),
        "recent_reports": [{"id": r.id, "title": r.title, "created_at": r.created_at.isoformat(), "project_id": r.project_id}
                           for r in q(m.Report).order_by(m.Report.created_at.desc()).limit(5).all()],
        "recent_activity": [{"type": "analysis", "id": a.id, "project_id": a.project_id, "status": a.status, "at": a.created_at.isoformat()} for a in recent],
        "system": {"database": "ok", "satellite": cdse.integration_status(), "llm": runtime.configured_summary()},
    }


class LLMSettingsIn(BaseModel):
    provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    xai_model: str | None = None


@router.get("/settings")
def get_settings_view():
    return {"llm": runtime.configured_summary(), "satellite": cdse.integration_status(),
            "limits": {"max_upload_mb": get_settings().max_upload_mb}, "secrets_note": "Secrets are read from environment variables and never returned."}


@router.put("/settings/llm")
def put_llm(body: LLMSettingsIn):
    try:
        runtime.update(**body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return runtime.configured_summary()
