from __future__ import annotations

import asyncio
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access, require_tenant_access
from kusys.persistence.database import get_db, SessionLocal
from kusys.persistence.models import Job
from kusys.jobs.service import cancel_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def serialize(job: Job) -> dict:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result,
        "error_code": job.error_code,
    }


def authorize_job(db: Session, actor: Actor, job: Job) -> None:
    if job.project_id:
        require_project_access(db, actor, job.project_id)
    elif job.tenant_id:
        require_tenant_access(db, actor, job.tenant_id)
    elif not actor.user.is_platform_admin:
        raise HTTPException(403, "Kein Zugriff auf diesen Job")


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    authorize_job(db, actor, job)
    return serialize(job)


@router.post("/{job_id}/cancel")
def cancel(job_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    authorize_job(db, actor, job)
    cancel_job(job)
    db.commit()
    return serialize(job)


@router.get("/{job_id}/events")
async def events(job_id: uuid.UUID, actor: Actor = Depends(require_actor)):
    # Authorize before opening a long-lived stream.
    with SessionLocal() as db:
        initial = db.get(Job, job_id)
        if not initial:
            raise HTTPException(404, "Job nicht gefunden")
        authorize_job(db, actor, initial)

    async def stream():
        last = None
        for _ in range(3600):
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if not job:
                    yield 'event: error\ndata: {"error":"not_found"}\n\n'
                    return
                data = serialize(job)
            encoded = json.dumps(data, default=str)
            if encoded != last:
                yield f"data: {encoded}\n\n"
                last = encoded
            if data["status"] in {"succeeded", "failed", "cancelled", "unknown"}:
                return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")
