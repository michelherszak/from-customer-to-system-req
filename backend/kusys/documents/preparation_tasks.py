"""Restart-safe document preparation previews; no existing review is modified."""
import uuid
from sqlalchemy import select
from kusys.persistence.models import Job, DocumentVersion, Document, Project, ExtractedBlock, AIProviderConfig, Tenant
from kusys.jobs.service import start_job, finish_job, fail_job, update_job
from kusys.common.security import decrypt_secret, utcnow
from kusys.common.config import get_settings
from kusys.analysis.providers import CrewAIProvider
from kusys.documents.preparation import prepare_blocks


def process_preparation(db, job_id):
    job = db.get(Job, job_id)
    if not job or job.kind != "document_prepare":
        raise ValueError("Aufbereitungsauftrag nicht gefunden")
    if job.status == "succeeded":
        return job.result
    if job.status == "cancel_requested":
        job.status = "cancelled"; job.finished_at = utcnow(); db.commit(); return {}
    try:
        version = db.get(DocumentVersion, uuid.UUID(job.payload["document_version_id"]))
        doc = db.get(Document, version.document_id) if version else None
        project = db.get(Project, job.project_id)
        if not doc or not project or doc.project_id != job.project_id or doc.deleted_at or version.status != "ready":
            raise ValueError("Dokument ist nicht mehr für die Aufbereitung verfügbar")
        start_job(job, "Gesamtdokument und Layout werden gelesen")
        db.commit()
        rows = list(db.scalars(select(ExtractedBlock).where(ExtractedBlock.document_version_id == version.id).order_by(ExtractedBlock.page_number, ExtractedBlock.block_index)))
        blocks = [{"id": str(x.id), "text": x.source_text, "page": x.page_number, "kind": x.block_type, "coordinates": x.coordinates, "table": x.table_meta} for x in rows]
        blocks.sort(key=lambda b: (b["page"] or 0, (b["coordinates"] or {}).get("y0", 0), (b["coordinates"] or {}).get("x0", 0)))
        provider = None
        if job.payload.get("provider_config_id"):
            cfg = db.get(AIProviderConfig, uuid.UUID(job.payload["provider_config_id"]))
            if not cfg or cfg.tenant_id != project.tenant_id or not cfg.endpoint or not cfg.encrypted_api_key or (project.confidential and not cfg.confidential_allowed):
                raise ValueError("Provider nicht für dieses Dokument freigegeben")
            model = job.payload["model_id"]
            if model not in (cfg.allowed_models or []):
                raise ValueError("Modell nicht freigegeben")
            provider = CrewAIProvider(cfg.provider, cfg.endpoint, decrypt_secret(cfg.encrypted_api_key, get_settings().master_key), model)
            tenant = db.get(Tenant, project.tenant_id)
            provider.instructions = (tenant.agent_settings or {}).get("instructions", {})
        update_job(job, 20, "Absätze und Tabellenzeilen werden rekonstruiert")
        db.commit()
        result = prepare_blocks(blocks, provider)
        db.refresh(job)
        if job.status == "cancel_requested":
            job.status = "cancelled"; job.finished_at = utcnow(); db.commit(); return {}
        result.update({"document_version_id": str(version.id), "document_id": str(doc.id), "filename": version.filename, "source_sha256": version.sha256, "original_blocks": blocks,
                       "provider": provider.provider_id if provider else None, "model": provider.model_id if provider else None})
        if provider:
            result["usage"] = {"input_tokens": provider.input_tokens, "output_tokens": provider.output_tokens}
        finish_job(job, result)
        job.message = "Dokumentaufbereitung fertig; Vorschau unter Dokumente. Bestehender Prüfschritt unverändert."
        db.commit()
        return result
    except Exception as exc:
        fail_job(job, "document_preparation_failed", str(exc)[:400] if isinstance(exc, ValueError) else "Aufbereitung fehlgeschlagen: " + type(exc).__name__)
        db.commit()
        raise
