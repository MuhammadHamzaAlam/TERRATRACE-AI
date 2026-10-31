"""Human verification workflow. Only humans (via explicit API calls) change review status; the LLM has no write path here."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import models as m

STATUSES = ("pending", "confirmed", "rejected", "needs_investigation")
LABELS = {"pending": "Pending review", "confirmed": "Confirmed change", "rejected": "Rejected detection",
          "needs_investigation": "Needs further investigation"}


class ReviewError(ValueError):
    pass


def set_status(db: Session, event: m.Event, new_status: str, reviewer: str, notes: str = "") -> m.EventHistory:
    if new_status not in STATUSES:
        raise ReviewError(f"Invalid status '{new_status}'. Allowed: {', '.join(STATUSES)}")
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ReviewError("A reviewer identity is required")
    if new_status == event.review_status and not notes.strip():
        raise ReviewError("Status unchanged; provide a note to record a comment")
    rec = m.EventHistory(event_id=event.id, previous_status=event.review_status, new_status=new_status,
                         reviewer=reviewer[:100], notes=notes.strip()[:4000])
    event.review_status = new_status
    db.add(rec); db.commit()
    return rec


def bulk_set_status(db: Session, event_ids: list[str], new_status: str, reviewer: str, notes: str, confirm: bool, project_id: str | None = None) -> int:
    if not confirm:
        raise ReviewError("Bulk review requires explicit confirmation (confirm=true)")
    if not event_ids or len(event_ids) > 500:
        raise ReviewError("Provide between 1 and 500 event ids")
    q = db.query(m.Event).filter(m.Event.id.in_(event_ids))
    if project_id:
        q = q.filter(m.Event.project_id == project_id)
    evs = q.all()
    if len(evs) != len(set(event_ids)):
        raise ReviewError("Some event ids were not found in this project")
    for e in evs:
        if e.review_status != new_status:
            set_status(db, e, new_status, reviewer, notes)
    return len(evs)
