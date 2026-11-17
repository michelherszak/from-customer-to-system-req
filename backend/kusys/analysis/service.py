from __future__ import annotations

import uuid
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.analysis.providers import AIProvider, CrewAIProvider
from kusys.common.security import utcnow, decrypt_secret
from kusys.common.config import get_settings
from kusys.jobs.service import create_job, fail_job, finish_job, start_job, update_job
from kusys.persistence.models import (
    AIModelPrice, AIProviderConfig, AIUsageEvent, AnalysisRun, AnalysisStep, ClarificationItem, Job, Project, Requirement, RequirementRevision,
    ReviewRevision, Section, ExtractedBlock, DocumentVersion, Job as SourceJob, Tenant, WorkPackage, WorkPackageRequirement, WorkPackageRevision, WorkPackageDependency,
)

MAX_CHARS = get_settings().analysis_max_chars

class AnalysisCancelled(Exception):
    pass


def create_analysis_run(db: Session, project_id: uuid.UUID, actor_id: uuid.UUID, provider_config_id: uuid.UUID | None = None, model_id: str | None = None, resume_from_run_id: uuid.UUID | None = None, recheck: bool = False) -> tuple[AnalysisRun, Job]:
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if not project or project.deleted_at:
        raise ValueError("Projekt nicht gefunden")
    active = db.scalar(select(AnalysisRun.id).where(AnalysisRun.project_id == project_id, AnalysisRun.status.in_(["running", "queued"])).limit(1))
    if active:
        raise ValueError("Für dieses Projekt läuft bereits eine Analyse")
    source = db.get(AnalysisRun, resume_from_run_id) if resume_from_run_id else None
    resumable = source and (source.status == "failed" or (source.status == "succeeded" and (source.result_json or {}).get("quality", {}).get("status") == "blocked" and source.activated_at is None))
    if resume_from_run_id and (not resumable or source.project_id != project_id):
        raise ValueError("Nur ein fehlgeschlagener oder im Review blockierter Lauf dieses Projekts kann fortgesetzt werden")
    tenant = db.get(Tenant, project.tenant_id)
    agent_settings = tenant.agent_settings or {}
    if provider_config_id is None and agent_settings.get("default_provider_config_id"):
        provider_config_id = uuid.UUID(agent_settings["default_provider_config_id"])
        model_id = model_id or agent_settings.get("default_model_id")
    if provider_config_id is None:
        raise ValueError("Kein KI-Modell gewählt. Cloud-Anbieter mit API-Schlüssel und Modell konfigurieren; Regelcode erzeugt keine Systemableitung.")
    review = db.scalar(
        select(ReviewRevision)
        .where(ReviewRevision.project_id == project_id)
        .order_by(ReviewRevision.revision_no.desc())
    )
    if not review or review.status != "approved":
        raise ValueError("Analyse benötigt eine freigegebene Prüfschrittrevision")
    if source and source.review_revision_id != review.id:
        raise ValueError("Prüfschritt wurde geändert. Bitte mit dem neuen Quellenstand frisch starten.")
    # PDF paragraphs must be reconstructed before downstream derivation.
    pdf_source = db.scalar(select(Section.id).join(ExtractedBlock, Section.extracted_block_id == ExtractedBlock.id).join(DocumentVersion, ExtractedBlock.document_version_id == DocumentVersion.id).where(Section.review_revision_id == review.id, Section.category == "requirement", Section.excluded.is_(False), Section.deleted_at.is_(None), DocumentVersion.mime_type == "application/pdf").limit(1))
    if pdf_source:
        preparation_id = (review.source_selection or {}).get("__preparation_job_id")
        preparation = db.get(SourceJob, uuid.UUID(preparation_id)) if preparation_id else None
        if not preparation or preparation.kind != "document_prepare" or preparation.project_id != project_id or preparation.status != "succeeded":
            raise ValueError("PDF-Absätze zuerst unter Dokumentaufbereitung zusammenführen, als neue Prüfschritt-Revision übernehmen und freigeben.")
    selected_provider = selected_model = ""
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
    if source and (source.provider != selected_provider or source.model_id != selected_model):
        raise ValueError("Modell wurde geändert. Bitte frisch starten.")
    review_seed = human_review = None
    if recheck:
        if not source or source.status != "succeeded" or (source.result_json or {}).get("quality", {}).get("status") != "blocked":
            raise ValueError("Nachprüfung benötigt einen abgeschlossenen Lauf mit offenen Befunden")
        from kusys.analysis.human_review import snapshot, response_step
        answers_step = response_step(db, source.id)
        if not answers_step or not (answers_step.result_json or {}).get("answers"):
            raise ValueError("Zuerst mindestens eine fachliche Antwort zu einem offenen Befund speichern")
        human_review = snapshot(db, source)
        review_seed = source.result_json
    elif source:
        previous_job = db.scalar(select(Job).where(Job.kind == "analysis", Job.payload["analysis_run_id"].as_string() == str(source.id)).order_by(Job.created_at.desc()))
        if previous_job:
            review_seed = (previous_job.payload or {}).get("review_seed")
            human_review = (previous_job.payload or {}).get("human_review")
    run = AnalysisRun(
        tenant_id=project.tenant_id,
        project_id=project_id,
        review_revision_id=review.id,
        provider=selected_provider,
        model_id=selected_model,
        schema_version="engineering-v2",
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
        payload={"analysis_run_id": str(run.id), "actor_id": str(actor_id), "provider_config_id": str(provider_config_id) if provider_config_id else None, "model_id": selected_model, "resume_from_run_id": str(resume_from_run_id) if resume_from_run_id else None, "agent_settings": agent_settings, "review_seed": review_seed, "human_review": human_review},
        idempotency_key=f"analysis:{run.id}",
    )
    db.commit()
    return run, job


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
            provider=CrewAIProvider(cfg.provider,cfg.endpoint,decrypt_secret(cfg.encrypted_api_key,get_settings().master_key),str(job.payload.get("model_id") or run.model_id))
        else:
            raise ValueError("Analyse ohne KI-Modell ist gesperrt")
    agent_settings = (job.payload or {}).get("agent_settings") or {}
    provider.instructions = agent_settings.get("instructions", {})
    max_rounds = agent_settings.get("max_rounds", 2)
    review_seed = (job.payload or {}).get("review_seed")
    human_review = (job.payload or {}).get("human_review")
    first_round = max((item["round"] for item in (review_seed or {}).get("review_history", [])), default=0) + 1
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
        from kusys.analysis.workflow import run_workflow
        def record_role(role, round_no, status, output):
            db.refresh(job)
            name = f"{role}:round-{round_no}"
            if job.status == "cancel_requested":
                entry = db.scalar(select(AnalysisStep).where(AnalysisStep.analysis_run_id == run.id, AnalysisStep.step_name == name))
                if entry:
                    data = entry.result_json or {"outputs": [], "events": []}
                    events = list(data.get("events", []))
                    for event in reversed(events):
                        if event.get("status") == "running":
                            event.update(status="cancelled", finished_at=utcnow().isoformat())
                            break
                    entry.result_json = {**data, "events": events}
                    entry.status = "cancelled"
                    db.commit()
                raise AnalysisCancelled()
            entry = db.scalar(select(AnalysisStep).where(AnalysisStep.analysis_run_id == run.id, AnalysisStep.step_name == name))
            if not entry:
                entry = AnalysisStep(analysis_run_id=run.id, step_name=name, status=status, created_by=actor_id)
                db.add(entry)
            entry.status = "succeeded" if status == "cached" else status
            previous = entry.result_json or {"outputs": []}
            events = list(previous.get("events", []))
            now = utcnow().isoformat()
            if status == "running":
                events.append({"status": status, "started_at": now, **(output or {})})
            elif role != "review_round" and events:
                events[-1] = {**events[-1], "status": status, "finished_at": now}
                if status == "failed":
                    events[-1].update(output or {})
                elif output:
                    events[-1]["counts"] = {key: len(value) for key, value in output.items() if isinstance(value, list)}
            outputs = list(previous.get("outputs", []))
            if output is not None and status in {"succeeded", "cached"}:
                outputs.append(output)
            entry.result_json = {"outputs": outputs, "events": events}
            batch = (output or {}).get("batch") if status == "running" else None
            detail = f" · Paket {batch['index']}/{batch['count']}" if batch else ""
            reused = " · aus Checkpoint übernommen" if status == "cached" else ""
            update_job(job, min(89, 10 + round_no * 22), f"Runde {round_no-first_round+1}/{max_rounds} · {role}{detail}{reused}")
            db.commit()
        from kusys.services.calculation import ensure_project_rate_card
        from kusys.persistence.models import RateCardRole
        card = ensure_project_rate_card(db, project, actor_id)
        role_names = sorted(db.scalars(select(RateCardRole.name).where(RateCardRole.rate_card_id == card.id)))
        from kusys.analysis.checkpoints import Checkpoints
        checkpoint_run_id = (job.payload or {}).get("resume_from_run_id")
        checkpoint_source = db.get(AnalysisRun, uuid.UUID(checkpoint_run_id)) if checkpoint_run_id else run
        entries = list(db.scalars(select(AnalysisStep).where(AnalysisStep.analysis_run_id == checkpoint_source.id).order_by(AnalysisStep.created_at)))
        def unchanged(value):
            # SQLite tests may return naive datetimes; timestamps are always UTC.
            from datetime import timezone
            return value.replace(tzinfo=timezone.utc) <= checkpoint_source.created_at.replace(tzinfo=timezone.utc)
        latest_section_edit = db.scalar(select(func.max(Section.updated_at)).where(Section.review_revision_id == review.id))
        latest_rate_edit = db.scalar(select(func.max(RateCardRole.updated_at)).where(RateCardRole.rate_card_id == card.id))
        legacy = bool(checkpoint_run_id and unchanged(project.updated_at) and unchanged(review.updated_at) and unchanged(card.updated_at) and (not latest_rate_edit or unchanged(latest_rate_edit)) and (not latest_section_edit or unchanged(latest_section_edit)) and not any(provider.instructions.values()) and checkpoint_source.schema_version == "engineering-v2")
        cache = Checkpoints(entries, allow_legacy=legacy)
        result = run_workflow(sections, provider, project.document_language,
            project={"name": project.name, "description": project.short_description, "roles": role_names},
            on_step=record_role, max_chars=MAX_CHARS, checkpoints=cache, max_rounds=max_rounds, review_seed=review_seed, human_review=human_review)
        from kusys.analysis.estimates import add_estimates
        if result["quality"]["status"] != "blocked":
            add_estimates(db, project.id, result)
        else:
            result["estimate_summary"]["basis"] = "Keine freigegebene Ableitung; Budget- und Terminberechnung gesperrt."
        requirements = result["requirements"]
        work_packages = result["work_packages"]
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
        if isinstance(provider,CrewAIProvider):
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
    except AnalysisCancelled:
        job.status = "cancelled"
        run.status = "failed"
        run.error_code = "cancelled"
        step.status = "cancelled"
        for entry in db.scalars(select(AnalysisStep).where(AnalysisStep.analysis_run_id == run.id, AnalysisStep.status == "running")):
            entry.status = "cancelled"
            data = entry.result_json or {"outputs": [], "events": []}
            events = list(data.get("events", []))
            for event in events:
                if event.get("status") == "running":
                    event.update(status="cancelled", finished_at=utcnow().isoformat())
            entry.result_json = {**data, "events": events}
        db.commit()
        return run, job
    except Exception as exc:
        run.status = "failed"
        run.error_code = "analysis_failed"
        step.status = "failed"
        step.result_json = {"error_code": type(exc).__name__}
        for entry in db.scalars(select(AnalysisStep).where(AnalysisStep.analysis_run_id == run.id, AnalysisStep.status == "running")):
            entry.status = "failed"
        fail_job(job, "analysis_failed", str(exc)[:400] if isinstance(exc, ValueError) else type(exc).__name__)
        db.commit()
        raise


def activate_run(db: Session, run: AnalysisRun, actor_id: uuid.UUID, acknowledge_assumptions: bool = False) -> dict:
    db.refresh(run, with_for_update=True)
    if run.status != "succeeded" or run.activated_at is not None:
        raise ValueError("Analyselauf kann nicht aktiviert werden")
    from kusys.analysis.derivation import derivation_findings
    if derivation_findings(run.result_json or {}):
        raise ValueError("Ableitung abgelehnt: Ersatzmodus oder kopierte Kundenanforderungen; neuer KI-Modelllauf erforderlich")
    quality = (run.result_json or {}).get("quality", {})
    if quality.get("status") == "blocked":
        raise ValueError("Review blockiert: offene Befunde zuerst klären; siehe Engineering-Review")
    if quality.get("status") == "needs_human_review" and not acknowledge_assumptions:
        raise ValueError("Vorläufige Ableitungen/Schätzungen benötigen ausdrückliche Bestätigung der Projektleitung")
    review = db.get(ReviewRevision, run.review_revision_id)
    latest_review = db.scalar(
        select(ReviewRevision)
        .where(ReviewRevision.project_id == run.project_id)
        .order_by(ReviewRevision.revision_no.desc())
    )
    if not review or not latest_review or latest_review.id != review.id or latest_review.status != "approved":
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

    # Retire only packages explicitly created by earlier engineering runs, never manual packages.
    old_runs = db.scalars(select(AnalysisRun).where(AnalysisRun.project_id == run.project_id, AnalysisRun.activated_at.is_not(None)))
    for previous in old_runs:
        for entry in ((previous.result_json or {}).get("activation_mapping", {}).get("work_packages", {})).values():
            old_wp = db.get(WorkPackage, uuid.UUID(entry["id"]))
            if old_wp and old_wp.deleted_at is None:
                old_wp.deleted_at = utcnow()
                old_wp.deleted_by = actor_id
                old_wp.delete_reason = f"Ersetzt durch Analyselauf {run.id}"
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
            source_refs=[{"section_id": item["source_section_id"], "analysis_run_id": str(run.id), "analysis_key": item.get("key")}],
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
                snapshot={**work_package_snapshot(wp), "analysis_run_id": str(run.id)},
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

    by_key = {item.get("key"): wp for item, wp in zip(result.get("work_packages", []), created_work_packages)}
    for item, wp in zip(result.get("work_packages", []), created_work_packages):
        for predecessor in dict.fromkeys(item.get("depends_on", [])):
            db.add(WorkPackageDependency(predecessor_id=by_key[predecessor].id, successor_id=wp.id, created_by=actor_id))

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
    from copy import deepcopy
    activated_result = deepcopy(run.result_json)
    activated_result["activation_mapping"] = {
        "requirements": {item.get("key", str(i)): {"id": str(req.id), "key": req.key} for i, (item, req) in enumerate(zip(result.get("requirements", []), created_requirements))},
        "work_packages": {item.get("key", str(i)): {"id": str(wp.id), "key": wp.key} for i, (item, wp) in enumerate(zip(result.get("work_packages", []), created_work_packages))},
    }
    if quality.get("status") == "needs_human_review":
        activated_result["quality"]["acknowledgement"] = {"actor_id": str(actor_id), "at": utcnow().isoformat()}
    run.result_json = activated_result
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
