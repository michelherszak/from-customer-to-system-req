from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.common.security import utcnow
from kusys.persistence.models import Job

VALID_STATES = {"queued", "running", "succeeded", "failed", "cancel_requested", "cancelled", "unknown"}


def create_job(db: Session, *, kind: str, tenant_id=None, project_id=None, payload: dict | None = None, idempotency_key: str | None = None) -> Job:
    if idempotency_key:
        existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key, Job.kind == kind))
        if existing:
            return existing
    job = Job(tenant_id=tenant_id, project_id=project_id, kind=kind, payload=payload or {}, idempotency_key=idempotency_key)
    db.add(job)
    db.flush()
    return job


def start_job(job: Job, message: str | None = None) -> None:
    job.status = "running"
    job.started_at = utcnow()
    job.progress = max(job.progress, 1)
    job.message = message


def update_job(job: Job, progress: int, message: str | None = None) -> None:
    job.progress = max(0, min(100, progress))
    if message is not None:
        job.message = message


def finish_job(job: Job, result: dict | None = None) -> None:
    job.status = "succeeded"
    job.progress = 100
    job.result = result or {}
    job.finished_at = utcnow()


def fail_job(job: Job, error_code: str, message: str) -> None:
    job.status = "failed"
    job.error_code = error_code
    job.message = message
    job.finished_at = utcnow()


def cancel_job(job: Job) -> None:
    if job.status in {"queued", "running"}:
        job.status = "cancel_requested"
