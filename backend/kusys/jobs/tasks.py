from __future__ import annotations

import uuid
from datetime import timedelta
from sqlalchemy import select

from kusys.common.security import utcnow
from kusys.jobs.celery_app import celery_app
from kusys.persistence.database import SessionLocal
from kusys.persistence.models import Job


def _document_extract(job_id: str, actor_id: str | None = None):
    from kusys.documents.tasks import process_document_extract
    with SessionLocal() as db:
        return process_document_extract(db, uuid.UUID(job_id), uuid.UUID(actor_id) if actor_id else None)


def _analysis(job_id: str, actor_id: str):
    from kusys.analysis.service import process_analysis_job
    with SessionLocal() as db:
        run, job = process_analysis_job(db, uuid.UUID(job_id), uuid.UUID(actor_id))
        return {"analysis_run_id": str(run.id), "status": run.status, "job_status": job.status}


def _recover_stale_jobs():
    if celery_app is None:
        return {"dispatched": 0}
    dispatched = 0
    stale_cutoff = utcnow() - timedelta(minutes=30)
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(Job).where(
                    (Job.status == "queued")
                    | ((Job.status == "running") & (Job.started_at < stale_cutoff))
                )
            )
        )
        for job in jobs:
            actor_id = str(job.created_by) if getattr(job, "created_by", None) else None
            # Actor IDs are copied into payload by API callers for restart-safe dispatch.
            actor_id = str(job.payload.get("actor_id") or actor_id or "")
            if job.status == "running":
                job.status = "queued"
                job.message = "Nach Worker-Neustart erneut eingeplant"
            if job.kind == "document_extract":
                document_extract_task.delay(str(job.id), actor_id or None)
                dispatched += 1
            elif job.kind == "analysis" and actor_id:
                analysis_task.delay(str(job.id), actor_id)
                dispatched += 1
        db.commit()
    return {"dispatched": dispatched}


if celery_app is not None:
    document_extract_task = celery_app.task(
        name="kusys.document_extract",
        bind=False,
        autoretry_for=(Exception,),
        retry_backoff=True,
        max_retries=3,
    )(_document_extract)
    analysis_task = celery_app.task(
        name="kusys.analysis",
        bind=False,
        autoretry_for=(Exception,),
        retry_backoff=True,
        max_retries=3,
    )(_analysis)
    recover_stale_jobs = celery_app.task(name="kusys.recover_stale_jobs")(_recover_stale_jobs)
else:
    document_extract_task = None
    analysis_task = None
    recover_stale_jobs = None
