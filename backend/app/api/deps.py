from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import models as m
from app.database.session import get_db


def reviewer_name(x_reviewer: str = Header(default="local-analyst", max_length=100)) -> str:
    return x_reviewer.strip() or "local-analyst"


def get_project_or_404(project_id: str, db: Session = Depends(get_db)) -> m.Project:
    p = db.get(m.Project, project_id)
    if not p:
        raise HTTPException(404, f"Project {project_id} not found")
    return p


def get_analysis_or_404(db: Session, analysis_id: str) -> m.Analysis:
    a = db.get(m.Analysis, analysis_id)
    if not a:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    return a


def get_event_or_404(db: Session, event_uid: str) -> m.Event:
    e = db.get(m.Event, event_uid)
    if not e:
        raise HTTPException(404, f"Event {event_uid} not found")
    return e
