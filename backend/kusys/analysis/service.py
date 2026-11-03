from __future__ import annotations

import uuid
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.analysis.providers import AIProvider, DeterministicProvider, OpenAICompatibleProvider
from kusys.common.security import utcnow, decrypt_secret
from kusys.common.config import get_settings
from kusys.jobs.service import create_job, fail_job, finish_job, start_job, update_job
from kusys.persistence.models import (
    AIModelPrice, AIProviderConfig, AIUsageEvent, AnalysisRun, AnalysisStep, ClarificationItem, Job, Project, Requirement, RequirementRevision,
    ReviewRevision, Section, WorkPackage, WorkPackageRequirement, WorkPackageRevision,
)

MAX_CHARS = get_settings().analysis_max_chars


def create_analysis_run(db: Session, project_id: uuid.UUID, actor_id: uuid.UUID, provider_config_id: uuid.UUID | None = None, model_id: str | None = None) -> tuple[AnalysisRun, Job]:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Projekt nicht gefunden")
    review = db.scalar(
        select(ReviewRevision)
        .where(ReviewRevision.project_id == project_id)
        .order_by(ReviewRevision.revision_no.desc())
    )
    if not review or review.status != "approved":
        raise ValueError("Analyse benötigt eine freigegebene Prüfschrittrevision")
    provider = DeterministicProvider()
    selected_provider=provider.provider_id;selected_model=provider.model_id
    if provider_config_id is not None:
        cfg=db.get(AIProviderConfig,provider_config_id)
        if not cfg or cfg.tenant_id!=project.tenant_id: raise ValueError("KI-Provider-Konfiguration nicht gefunden")
        if project.confidential and not cfg.confidential_allowed: raise ValueError("Provider ist für vertrauliche Projekte nicht freigegeben")
        if not cfg.endpoint or not cfg.encrypted_api_key: raise ValueError("Provider benötigt Endpoint und API-Schlüssel")
        selected_model=model_id or "auto"
        if selected_model == "auto": selected_model = cfg.allowed_models[0] if cfg.allowed_models else None
        if not selected_model: raise ValueError("Kein Modell konfiguriert")
        if cfg.allowed_models and selected_model not in cfg.allowed_models: raise ValueError("Modell ist für diesen Provider nicht freigegeben")
        selected_provider=cfg.provider
    run = AnalysisRun(
        tenant_id=project.tenant_id,
        project_id=project_id,
        review_revision_id=review.id,
        provider=selected_provider,
        model_id=selected_model,
        schema_version="1",
        status="queued",
        created_by=actor_id,
    )
    db.add(run)
    db.flush()
    job = create_job(
        db,
        kind="analysis",
        tenant_id=project.tenant_id,
        project_id=project_id,
        payload={"analysis_run_id": str(run.id), "actor_id": str(actor_id), "provider_config_id": str(provider_config_id) if provider_config_id else None, "model_id": selected_model},
        idempotency_key=f"analysis:{run.id}",
    )
    db.commit()
    return run, job


def _chunk_sections(sections: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    count = 0
    for item in sections:
        if current and count + len(item[1]) > MAX_CHARS:
            chunks.append(current)
            current = []
            count = 0
        current.append(item)
        count += len(item[1])
    if current:
        chunks.append(current)
    return chunks


def process_analysis_job(
    db: Session,
    job_id: uuid.UUID,
    actor_id: uuid.UUID,
    provider: AIProvider | None = None,
) -> tuple[AnalysisRun, Job]:
    job = db.get(Job, job_id)
    if not job or job.kind != "analysis":
        raise ValueError("Analysejob nicht gefunden")
    run_id = uuid.UUID(str(job.payload["analysis_run_id"]))
    run = db.get(AnalysisRun, run_id)
    if not run:
        fail_job(job, "analysis_run_missing", "Analyselauf nicht gefunden")
        db.commit()
        raise ValueError("Analyselauf nicht gefunden")
    if job.status == "succeeded" and run.status in {"succeeded", "activated"}:
        return run, job
    if job.status == "cancel_requested":
        job.status = "cancelled"
        run.status = "failed"
        run.error_code = "cancelled"
        db.commit()
        return run, job

    if provider is None:
        cfg_id=job.payload.get("provider_config_id") if job.payload else None
        if cfg_id:
            cfg=db.get(AIProviderConfig,uuid.UUID(str(cfg_id)))
            if not cfg or not cfg.endpoint or not cfg.encrypted_api_key: raise ValueError("KI-Provider-Konfiguration ist nicht verwendbar")
            provider=OpenAICompatibleProvider(cfg.provider,cfg.endpoint,decrypt_secret(cfg.encrypted_api_key,get_settings().master_key),str(job.payload.get("model_id") or run.model_id))
        else:
            provider=DeterministicProvider()
    run.provider = provider.provider_id
    run.model_id = provider.model_id
    run.status = "running"
    start_job(job, "Analyse gestartet")
    step = db.scalar(
        select(AnalysisStep).where(
            AnalysisStep.analysis_run_id == run.id,
            AnalysisStep.step_name == "requirements_engineer",
        )
    )
    if not step:
        step = AnalysisStep(
            analysis_run_id=run.id,
            step_name="requirements_engineer",
            status="running",
            created_by=actor_id,
        )
        db.add(step)
    else:
        step.status = "running"
        step.result_json = None
    db.commit()

    try:
        review = db.get(ReviewRevision, run.review_revision_id)
        project = db.get(Project, run.project_id)
        if not review or not project:
            raise ValueError("Analyse-Eingabestand ist nicht mehr verfügbar")
        sections = [
            (str(s.id), s.edited_text)
            for s in db.scalars(
                select(Section)
                .where(
                    Section.review_revision_id == review.id,
                    Section.category == "requirement",
                    Section.excluded.is_(False),
                    Section.deleted_at.is_(None),
                )
                .order_by(Section.order_index)
            )
        ]
        if not sections:
            raise ValueError("Keine aktiven Anforderungsabschnitte vorhanden")
        chunks = _chunk_sections(sections)
        outputs = []
        for index, chunk in enumerate(chunks, start=1):
            if db.get(Job, job.id).status == "cancel_requested":
                job.status = "cancelled"
                run.status = "failed"
                run.error_code = "cancelled"
                db.commit()
                return run, job
            outputs.append(provider.analyze(chunk, project.document_language))
            update_job(job, min(85, int(index / max(1, len(chunks)) * 80)), f"Analyseblock {index}/{len(chunks)}")
            db.commit()

        requirements = []
        work_packages = []
        clarifications = []
        seen: set[str] = set()
        for output in outputs:
            index_map: dict[int, int] = {}
            for old_index, req in enumerate(output.requirements):
                key = " ".join(req.text.lower().split())
                if key in seen:
                    continue
                seen.add(key)
                index_map[old_index] = len(requirements)
                requirements.append(req)
            for wp in output.work_packages:
                mapped = tuple(index_map[i] for i in wp.requirement_indexes if i in index_map)
                if mapped:
                    from dataclasses import replace
                    work_packages.append(replace(wp, requirement_indexes=mapped))
            clarifications.extend(output.clarifications)

        result = {
            "requirements": [
                {
                    "text": x.text,
                    "priority": x.priority,
                    "title": x.title,
                    "source_section_id": x.source_section_id,
                }
                for x in requirements
            ],
            "work_packages": [
                {
                    "name": x.name,
                    "description": x.description,
                    "role": x.role,
                    "min_hours": x.min_hours,
                    "likely_hours": x.likely_hours,
                    "max_hours": x.max_hours,
                    "phase": x.phase,
                    "requirement_indexes": list(x.requirement_indexes),
                }
                for x in work_packages
            ],
            "clarifications": [
                {"text": x.text, "source_section_id": x.source_section_id}
                for x in clarifications
            ],
        }
        run.result_json = result
        run.status = "succeeded"
        step.status = "succeeded"
        step.result_json = {"requirements": len(requirements), "work_packages": len(work_packages)}
        update_job(job, 90, "Analyse abgeschlossen; Ergebnis bereit zur Aktivierung")
        finish_job(
            job,
            {
                "analysis_run_id": str(run.id),
                "requirements": len(requirements),
                "work_packages": len(work_packages),
            },
        )
        if isinstance(provider,OpenAICompatibleProvider):
            price=db.scalar(select(AIModelPrice).where(AIModelPrice.provider==provider.provider_id,AIModelPrice.model_id==provider.model_id).order_by(AIModelPrice.valid_from.desc()))
            provider_cost=0
            currency="EUR"
            if price:
                from decimal import Decimal
                provider_cost=(Decimal(provider.input_tokens)*Decimal(price.input_per_million)+Decimal(provider.output_tokens)*Decimal(price.output_per_million))/Decimal(1_000_000)
                currency=price.currency
            db.add(AIUsageEvent(tenant_id=run.tenant_id,project_id=run.project_id,analysis_run_id=run.id,provider=provider.provider_id,model_id=provider.model_id,input_tokens=provider.input_tokens,output_tokens=provider.output_tokens,provider_cost=provider_cost,provider_currency=currency,fx_rate_to_eur=1,cost_eur=provider_cost,status="success",created_by=actor_id))
        db.commit()
        return run, job
    except Exception as exc:
        run.status = "failed"
        run.error_code = "analysis_failed"
        step.status = "failed"
        step.result_json = {"error_code": type(exc).__name__}
        fail_job(job, "analysis_failed", type(exc).__name__)
        db.commit()
        raise


def create_and_run(
    db: Session,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
    provider: AIProvider | None = None,
) -> tuple[AnalysisRun, Job]:
    run, job = create_analysis_run(db, project_id, actor_id)
    return process_analysis_job(db, job.id, actor_id, provider)


def activate_run(db: Session, run: AnalysisRun, actor_id: uuid.UUID) -> dict:
    if run.status != "succeeded" or run.activated_at is not None:
        raise ValueError("Analyselauf kann nicht aktiviert werden")
    review = db.get(ReviewRevision, run.review_revision_id)
    latest_review = db.scalar(
        select(ReviewRevision)
        .where(ReviewRevision.project_id == run.project_id)
        .order_by(ReviewRevision.revision_no.desc())
    )
    if not latest_review or latest_review.id != review.id or latest_review.status != "approved":
        run.stale = True
        db.commit()
        raise ValueError("Analyselauf ist durch geänderte Eingaben veraltet")

    for existing in db.scalars(
        select(Requirement).where(
            Requirement.project_id == run.project_id,
            Requirement.deleted_at.is_(None),
            Requirement.origin == "analysis",
        )
    ):
        existing.deleted_at = utcnow()
        existing.deleted_by = actor_id
        existing.delete_reason = f"Ersetzt durch Analyselauf {run.id}"

    result = run.result_json or {}
    current_max = 0
    for key in db.scalars(select(Requirement.key).where(Requirement.project_id == run.project_id)):
        try:
            current_max = max(current_max, int(key.split("-")[-1]))
        except Exception:
            pass
    created_requirements: list[Requirement] = []
    for item in result.get("requirements", []):
        current_max += 1
        req = Requirement(
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            key=f"REQ-{current_max:04d}",
            title=item["title"],
            text=item["text"],
            priority=item["priority"],
            origin="analysis",
            source_refs=[{"section_id": item["source_section_id"]}],
            created_by=actor_id,
        )
        db.add(req)
        db.flush()
        db.add(
            RequirementRevision(
                requirement_id=req.id,
                revision_no=1,
                snapshot=requirement_snapshot(req),
                created_by=actor_id,
            )
        )
        created_requirements.append(req)

    wp_max = 0
    for key in db.scalars(select(WorkPackage.key).where(WorkPackage.project_id == run.project_id)):
        try:
            wp_max = max(wp_max, int(key.split("-")[-1]))
        except Exception:
            pass
    created_work_packages = []
    for item in result.get("work_packages", []):
        wp_max += 1
        likely = int(item["likely_hours"])
        wp = WorkPackage(
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            key=f"AP-{wp_max:03d}",
            name=item["name"],
            description=item["description"],
            role_name=item["role"],
            min_hours=int(item["min_hours"]),
            likely_hours=likely,
            max_hours=int(item["max_hours"]),
            plan_hours=likely,
            phase=item["phase"],
            created_by=actor_id,
        )
        db.add(wp)
        db.flush()
        db.add(
            WorkPackageRevision(
                work_package_id=wp.id,
                revision_no=1,
                snapshot=work_package_snapshot(wp),
                created_by=actor_id,
            )
        )
        for index in item.get("requirement_indexes", []):
            if 0 <= index < len(created_requirements):
                db.add(
                    WorkPackageRequirement(
                        work_package_id=wp.id,
                        requirement_id=created_requirements[index].id,
                        created_by=actor_id,
                    )
                )
        created_work_packages.append(wp)

    clarification_max = (
        db.scalar(
            select(func.count(ClarificationItem.id)).where(
                ClarificationItem.project_id == run.project_id
            )
        )
        or 0
    )
    for item in result.get("clarifications", []):
        clarification_max += 1
        db.add(
            ClarificationItem(
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                key=f"CLR-{clarification_max:04d}",
                text=item["text"],
                origin="automatic",
                source_refs=[{"section_id": item["source_section_id"]}],
                created_by=actor_id,
            )
        )
    run.activated_at = utcnow()
    run.status = "activated"
    db.commit()
    return {"requirements": len(created_requirements), "work_packages": len(created_work_packages)}


def requirement_snapshot(req: Requirement) -> dict:
    return {
        "key": req.key,
        "title": req.title,
        "text": req.text,
        "priority": req.priority,
        "budget_eur": str(req.budget_eur) if req.budget_eur is not None else None,
        "max_price_eur": str(req.max_price_eur) if req.max_price_eur is not None else None,
        "source_refs": req.source_refs,
        "origin": req.origin,
    }


def work_package_snapshot(wp: WorkPackage) -> dict:
    return {
        "key": wp.key,
        "name": wp.name,
        "description": wp.description,
        "role_name": wp.role_name,
        "min_hours": wp.min_hours,
        "likely_hours": wp.likely_hours,
        "max_hours": wp.max_hours,
        "plan_hours": wp.plan_hours,
        "max_fte": str(wp.max_fte),
        "planning_priority": wp.planning_priority,
        "phase": wp.phase,
        "global_package": wp.global_package,
        "scaling_mode": wp.scaling_mode,
    }
