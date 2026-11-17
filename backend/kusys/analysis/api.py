from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.analysis.service import activate_run, create_analysis_run, process_analysis_job
from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.persistence.database import get_db
from kusys.persistence.models import AnalysisRun, AnalysisStep, AIProviderConfig, Project, Job, Tenant, Section

router = APIRouter(tags=["analysis"])

class ActivationRequest(BaseModel):
    acknowledge_assumptions: bool = False


class AnalysisRequest(BaseModel):
    resume_from_run_id: uuid.UUID | None = None
    recheck: bool = False
    provider_config_id: uuid.UUID | None = None
    model_id: str | None = None


def serialize(r: AnalysisRun) -> dict:
    from kusys.analysis.derivation import assessed_result
    return {"id": str(r.id), "tenant_id": str(r.tenant_id), "project_id": str(r.project_id), "review_revision_id": str(r.review_revision_id), "provider": r.provider, "model_id": r.model_id, "schema_version": r.schema_version, "status": r.status, "stale": r.stale, "activated_at": r.activated_at, "result": assessed_result(r.result_json), "error_code": r.error_code}

@router.get("/projects/{project_id}/analysis-runs")
def list_runs(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    return [serialize(x) for x in db.scalars(select(AnalysisRun).where(AnalysisRun.project_id == project_id).order_by(AnalysisRun.created_at.desc()))]

@router.post("/projects/{project_id}/analysis-runs", status_code=202)
def run_analysis(project_id: uuid.UUID, payload: AnalysisRequest | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin"})
    try:
        payload=payload or AnalysisRequest()
        if payload.recheck:
            require_project_access(db,actor,project_id,{"project_lead","company_admin"})
        run, job = create_analysis_run(db, project_id, actor.user.id, payload.provider_config_id, payload.model_id, payload.resume_from_run_id, payload.recheck)
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

def restart_request(run_id, resume, db, actor, recheck=False):
    source = db.get(AnalysisRun, run_id)
    if not source:
        raise HTTPException(404, "Analyselauf nicht gefunden")
    require_project_access(db, actor, source.project_id, {"project_lead", "project_member", "company_admin"})
    source_job = db.scalar(select(Job).where(Job.project_id == source.project_id, Job.kind == "analysis", Job.payload["analysis_run_id"].as_string() == str(source.id)).order_by(Job.created_at.desc()))
    if not source_job or not source_job.payload.get("provider_config_id"):
        raise HTTPException(422, "Modellkonfiguration fehlt; bitte im Prüfschritt einen neuen Lauf starten")
    defaults = db.get(Tenant, source.tenant_id).agent_settings or {}
    provider_id = source_job.payload["provider_config_id"]
    model_id = source.model_id
    if not resume and defaults.get("default_provider_config_id"):
        provider_id, model_id = defaults["default_provider_config_id"], defaults["default_model_id"]
    return run_analysis(source.project_id, AnalysisRequest(
        provider_config_id=provider_id, model_id=model_id,
        resume_from_run_id=source.id if resume else None, recheck=recheck), db, actor)


@router.post("/analysis-runs/{run_id}/resume", status_code=202)
def resume(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    return restart_request(run_id, True, db, actor)


@router.post("/analysis-runs/{run_id}/restart", status_code=202)
def restart(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    return restart_request(run_id, False, db, actor)


class FindingAnswer(BaseModel):
    finding_id: str
    response: str = Field(min_length=1,max_length=6000)
    expected_version: int = Field(ge=0)


def review_response_data(db,run,actor):
    from kusys.analysis.human_review import findings,snapshot,response_step
    data=snapshot(db,run)
    step=response_step(db,run.id)
    try:
        require_project_access(db,actor,run.project_id,{"project_lead","company_admin"})
        authorized=True
    except HTTPException:
        authorized=False
    writable=authorized and run.status=="succeeded" and (run.result_json or {}).get("quality",{}).get("status")=="blocked" and run.activated_at is None
    targets={item["key"]:item for field in ("requirements","system_requirements","architecture","work_packages") for item in (run.result_json or {}).get(field,[])}
    source_sections={str(section.id):section for section in db.scalars(select(Section).where(Section.review_revision_id==run.review_revision_id))}
    answers={answer["finding_id"]:answer for answer in data["answers"]}
    return {"version":data["version"],"can_respond":writable,"can_recheck":writable and bool(step and (step.result_json or {}).get("answers")),
        "findings":[{**item,"target_text":targets.get(item["target_key"],{}).get("text",targets.get(item["target_key"],{}).get("description","")),"source_text":getattr(source_sections.get(item["target_key"]),"edited_text",None),"answer":answers.get(item["finding_id"])} for item in findings(run)]}


@router.get("/analysis-runs/{run_id}/review-responses")
def review_responses(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    run=db.get(AnalysisRun,run_id)
    if not run:raise HTTPException(404,"Analyselauf nicht gefunden")
    require_project_access(db,actor,run.project_id)
    return review_response_data(db,run,actor)


@router.post("/analysis-runs/{run_id}/review-responses")
def answer_finding(run_id: uuid.UUID, payload: FindingAnswer, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    from kusys.analysis.human_review import findings,response_step
    from kusys.common.security import utcnow
    run=db.scalar(select(AnalysisRun).where(AnalysisRun.id==run_id).with_for_update())
    if not run:raise HTTPException(404,"Analyselauf nicht gefunden")
    require_project_access(db,actor,run.project_id,{"project_lead","company_admin"})
    if not review_response_data(db,run,actor)["can_respond"]:raise HTTPException(409,"Dieser Lauf kann nicht mehr beantwortet werden")
    finding=next((item for item in findings(run) if item["finding_id"]==payload.finding_id),None)
    if not finding:raise HTTPException(422,"Befund gehört nicht zu den offenen Fragen dieses Laufs")
    response=payload.response.strip()
    if not response:raise HTTPException(422,"Bitte eine fachliche Antwort eingeben")
    step=response_step(db,run.id)
    previous=(step.result_json or {}) if step else {}
    if previous.get("version",0)!=payload.expected_version:raise HTTPException(409,"Antworten wurden inzwischen geändert; bitte neu laden")
    record={**finding,"response":response,"actor_id":str(actor.user.id),"actor_name":actor.user.display_name,"answered_at":utcnow().isoformat(),"source_run_id":str(run.id)}
    if not step:
        step=AnalysisStep(analysis_run_id=run.id,step_name="human_review",status="saved",created_by=actor.user.id);db.add(step)
    step.result_json={"version":payload.expected_version+1,"answers":{**previous.get("answers",{}),payload.finding_id:record},"history":[*previous.get("history",[]),record]}
    db.commit()
    return review_response_data(db,run,actor)


@router.post("/analysis-runs/{run_id}/recheck",status_code=202)
def recheck(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    source=db.get(AnalysisRun,run_id)
    if not source:raise HTTPException(404,"Analyselauf nicht gefunden")
    require_project_access(db,actor,source.project_id,{"project_lead","company_admin"})
    return restart_request(run_id,True,db,actor,recheck=True)


@router.post("/analysis-runs/{run_id}/activate")
def activate(run_id: uuid.UUID, payload: ActivationRequest | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    run = db.get(AnalysisRun, run_id)
    if not run: raise HTTPException(404, "Analyselauf nicht gefunden")
    require_project_access(db, actor, run.project_id, {"project_lead", "company_admin"})
    try: result = activate_run(db, run, actor.user.id, (payload or ActivationRequest()).acknowledge_assumptions)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    return {"analysis_run": serialize(run), **result}


@router.get("/analysis-runs/{run_id}/steps")
def steps(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Analyselauf nicht gefunden")
    require_project_access(db, actor, run.project_id)
    return [{"name": x.step_name, "status": x.status, "result": x.result_json} for x in db.scalars(select(AnalysisStep).where(AnalysisStep.analysis_run_id == run_id).order_by(AnalysisStep.created_at))]


@router.get("/analysis-runs/{run_id}/diagnostics")
def diagnostics(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Analyselauf nicht gefunden")
    require_project_access(db, actor, run.project_id)
    entries = list(db.scalars(select(AnalysisStep).where(AnalysisStep.analysis_run_id == run_id).order_by(AnalysisStep.created_at)))
    job = db.scalar(select(Job).where(Job.kind == "analysis", Job.project_id == run.project_id, Job.payload["analysis_run_id"].as_string() == str(run.id)).order_by(Job.created_at.desc()))
    reused = sum(e.get("status") == "cached" for entry in entries for e in (entry.result_json or {}).get("events", []))
    return {"run_id": str(run.id), "status": run.status, "provider": run.provider,
        "job_id": str(job.id) if job else None, "job_status": job.status if job else None,
        "resume_from_run_id": (job.payload or {}).get("resume_from_run_id") if job else None, "cached_packages": reused,
        "model_id": run.model_id, "error_code": run.error_code,
        "steps": [{"name": x.step_name, "status": x.status, "events": (x.result_json or {}).get("events", [])} for x in entries]}


@router.get("/analysis-runs/{run_id}/documentation")
def documentation(run_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    from fastapi.responses import Response
    from kusys.analysis.documentation import render_documentation
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Analyselauf nicht gefunden")
    require_project_access(db, actor, run.project_id)
    if not run.result_json:
        raise HTTPException(409, "Noch kein Ergebnis verfügbar")
    return Response(render_documentation(run), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="KuSys-Engineering-{run.id}.md"'})


@router.get("/projects/{project_id}/analysis-options")
def analysis_options(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    project = db.get(Project, project_id)
    settings = db.get(Tenant, project.tenant_id).agent_settings or {}
    rows = [{"id": str(x.id), "provider": x.provider, "models": sorted(x.allowed_models, key=lambda model: model != settings.get("default_model_id")), "is_default": str(x.id) == settings.get("default_provider_config_id")} for x in db.scalars(select(AIProviderConfig).where(AIProviderConfig.tenant_id == project.tenant_id)) if x.endpoint and x.encrypted_api_key and x.allowed_models and (not project.confidential or x.confidential_allowed)]
    return sorted(rows, key=lambda row: not row["is_default"])
