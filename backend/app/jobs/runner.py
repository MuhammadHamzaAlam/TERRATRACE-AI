"""Persistent local background job runner (thread pool; job state stored in the DB so it survives polling/restarts)."""
from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from app.database import models as m
from app.database.session import SessionLocal

log = logging.getLogger("terratrace.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tt-job")


def mark_interrupted_jobs():
    """On startup, jobs left queued/running by a previous process can never finish: mark them failed."""
    with SessionLocal() as db:
        for j in db.query(m.Job).filter(m.Job.status.in_(["queued", "running"])).all():
            j.status, j.message = "failed", "Interrupted by server restart"
        for a in db.query(m.Analysis).filter(m.Analysis.status.in_(["pending", "running"])).all():
            if a.status == "running":
                a.status, a.status_message = "failed", "Interrupted by server restart"
        for t in db.query(m.TrainingRun).filter(m.TrainingRun.status.in_(["pending", "running"])).all():
            t.status, t.message = "failed", "Interrupted by server restart"
        db.commit()


def submit(kind: str, ref_id: str | None, fn: Callable[[Callable[[float, str], None]], None], sync: bool = False) -> str:
    with SessionLocal() as db:
        job = m.Job(kind=kind, ref_id=ref_id, status="queued")
        db.add(job); db.commit(); job_id = job.id

    def update(progress: float, message: str = ""):
        with SessionLocal() as db:
            j = db.get(m.Job, job_id)
            j.progress, j.message, j.status = float(progress), message, "running"
            db.commit()

    def run():
        try:
            update(0.0, "started")
            fn(update)
            with SessionLocal() as db:
                j = db.get(m.Job, job_id); j.status, j.progress = "completed", 1.0; db.commit()
        except Exception as e:  # noqa: BLE001 - job boundary
            log.error("job %s failed: %s\n%s", job_id, e, traceback.format_exc())
            with SessionLocal() as db:
                j = db.get(m.Job, job_id); j.status, j.message = "failed", str(e)[:1000]; db.commit()

    if sync:
        run()
    else:
        _pool.submit(run)
    return job_id
