from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.analysis.service import activate_run, create_analysis_run, process_analysis_job
from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.persistence.database import get_db
from kusys.persistence.models import AnalysisRun

router = APIRouter(tags=["analysis"])

class AnalysisRequest(BaseModel):
    provider_config_id: uuid.UUID | None = None
    model_id: str | None = None


def serialize(r: AnalysisRun) -> dict:
    return {"id": str(r.id), "project_id": str(r.project_id), "review_revision_id": str(r.review_revision_id), "provider": r.provider, "model_id": r.model_id, "schema_version": r.schema_version, "status": r.status, "stale": r.stale, "activated_at": r.activated_at, "result": r.result_json, "error_code": r.error_code}

@router.get("/projects/{project_id}/analysis-runs")
def list_runs(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    return [serialize(x) for x in db.scalars(select(AnalysisRun).where(AnalysisRun.project_id == project_id).order_by(AnalysisRun.created_at.desc()))]

@router.post("/projects/{project_id}/analysis-runs", status_code=202)
def run_analysis(project_id: uuid.UUID, payload: AnalysisRequest | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin"})
    try:
        payload=payload or AnalysisRequest()
        run, job = create_analysis_run(db, project_id, actor.user.id, payload.provider_config_id, payload.model_id)
        from kusys.common.config import get_settings
        if get_settings().inline_jobs:
            run, job = process_analysis_job(db, job.id, actor.user.id)
        else:
            from kusys.jobs.tasks import analysis_task
            if analysis_task is None:
                raise HTTPException(503, "Worker ist nicht verfügbar")
            analysis_task.delay(str(job.id), str(actor.user.id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"analysis_run": serialize(run), "job_id": str(job.id)}

@router.post("/analysis-runs/{run_id}/activate")
def activate(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    run = db.get(AnalysisRun, run_id)
    if not run: raise HTTPException(404, "Analyselauf nicht gefunden")
    require_project_access(db, actor, run.project_id, {"project_lead", "company_admin"})
    try: result = activate_run(db, run, actor.user.id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    return {"analysis_run": serialize(run), **result}
