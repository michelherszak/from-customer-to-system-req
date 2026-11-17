from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.artifacts.storage import storage
from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.locking import bump_version
from kusys.common.security import utcnow
from kusys.documents.service import validate_upload
from kusys.documents.tasks import process_document_extract
from kusys.jobs.service import create_job
from kusys.persistence.database import get_db
from kusys.persistence.models import Document, DocumentVersion, ExtractedBlock

router = APIRouter(tags=["documents"])


def serialize_document(d: Document) -> dict:
    return {"id": str(d.id), "project_id": str(d.project_id), "name": d.name, "kind": d.kind, "lock_version": d.lock_version}


def serialize_version(v: DocumentVersion) -> dict:
    return {"id": str(v.id), "document_id": str(v.document_id), "version": v.version, "filename": v.filename, "mime_type": v.mime_type, "size_bytes": v.size_bytes, "sha256": v.sha256, "status": v.status, "page_count": v.page_count, "extraction_meta": v.extraction_meta}

@router.get("/projects/{project_id}/documents")
def list_documents(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    docs = list(db.scalars(select(Document).where(Document.project_id == project_id, Document.deleted_at.is_(None)).order_by(Document.created_at)))
    out = []
    for d in docs:
        versions = list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id).order_by(DocumentVersion.version.desc())))
        out.append({**serialize_document(d), "versions": [serialize_version(v) for v in versions]})
    return out

@router.post("/projects/{project_id}/documents", status_code=202)
async def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    document_id: uuid.UUID | None = Form(None),
    document_name: str | None = Form(None),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_csrf),
):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin"})
    data = await file.read()
    try:
        ext, expected_mime = validate_upload(file.filename or "upload", file.content_type, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if document_id:
        doc = db.get(Document, document_id)
        if not doc or doc.project_id != project_id: raise HTTPException(404, "Dokument nicht gefunden")
    else:
        from kusys.persistence.models import Project
        project = db.get(Project, project_id)
        doc = Document(tenant_id=project.tenant_id, project_id=project_id, name=document_name or Path(file.filename or "Dokument").stem, created_by=actor.user.id)
        db.add(doc); db.flush()
    next_version = (db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == doc.id)) or 0) + 1
    artifact, path = storage.put_bytes(data, tenant_id=doc.tenant_id, project_id=project_id, filename=file.filename or f"document{ext}", mime_type=expected_mime)
    # DocumentVersion is the authoritative metadata row for source documents; FileArtifact is intentionally not duplicated.
    version = DocumentVersion(
        tenant_id=doc.tenant_id, document_id=doc.id, version=next_version, filename=file.filename or "document",
        mime_type=expected_mime, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), storage_key=artifact.storage_key,
        status="uploaded", created_by=actor.user.id,
    )
    db.add(version); db.flush()
    job = create_job(db, kind="document_extract", tenant_id=doc.tenant_id, project_id=project_id, payload={"document_version_id": str(version.id), "actor_id": str(actor.user.id)})
    db.commit()
    from kusys.common.config import get_settings
    if get_settings().inline_jobs:
        process_document_extract(db, job.id, actor.user.id)
        db.refresh(version)
    else:
        from kusys.jobs.tasks import document_extract_task
        if document_extract_task is None:
            raise HTTPException(503, "Worker ist nicht verfügbar")
        document_extract_task.delay(str(job.id), str(actor.user.id))
    return {"document": serialize_document(doc), "version": serialize_version(version), "job_id": str(job.id)}

@router.delete("/documents/{document_id}")
def delete_document(document_id: uuid.UUID, reason: str = "Vom Benutzer gelöscht", db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at is not None:
        raise HTTPException(404, "Dokument nicht gefunden")
    require_project_access(db, actor, doc.project_id, {"project_lead"})
    if not reason.strip():
        raise HTTPException(422, "Löschgrund ist erforderlich")
    doc.deleted_at = utcnow()
    doc.deleted_by = actor.user.id
    doc.delete_reason = reason.strip()
    bump_version(doc)
    db.commit()
    return {"ok": True, "id": str(doc.id)}

@router.get("/documents/{document_id}/versions")
def versions(document_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Dokument nicht gefunden")
    require_project_access(db, actor, doc.project_id)
    return [serialize_version(v) for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(DocumentVersion.version))]

@router.get("/document-versions/{version_id}/blocks")
def blocks(version_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    v = db.get(DocumentVersion, version_id)
    if not v: raise HTTPException(404, "Dokumentversion nicht gefunden")
    doc = db.get(Document, v.document_id); require_project_access(db, actor, doc.project_id)
    rows = db.scalars(select(ExtractedBlock).where(ExtractedBlock.document_version_id == version_id).order_by(ExtractedBlock.page_number, ExtractedBlock.block_index))
    return [{"id": str(b.id), "page_number": b.page_number, "block_index": b.block_index, "block_type": b.block_type, "source_text": b.source_text, "normalized_text": b.normalized_text, "coordinates": b.coordinates, "table_meta": b.table_meta, "text_source": b.text_source, "quality_status": b.quality_status} for b in rows]


class PreparationRequest(BaseModel):
    document_version_id: uuid.UUID
    provider_config_id: uuid.UUID | None = None
    model_id: str | None = None


@router.post("/projects/{project_id}/document-preparations", status_code=202)
def prepare_document(project_id: uuid.UUID, payload: PreparationRequest, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    from kusys.persistence.models import AIProviderConfig, Project
    from kusys.common.config import get_settings
    require_project_access(db, actor, project_id)
    version = db.get(DocumentVersion, payload.document_version_id)
    doc = db.get(Document, version.document_id) if version else None
    if not doc or doc.project_id != project_id or doc.deleted_at or version.status != "ready":
        raise HTTPException(422, "Nur fertig extrahierte Dokumentversionen dieses Projekts können aufbereitet werden")
    model = None
    if payload.provider_config_id:
        cfg = db.get(AIProviderConfig, payload.provider_config_id)
        project = db.get(Project, project_id)
        if not cfg or cfg.tenant_id != project.tenant_id or not cfg.endpoint or not cfg.encrypted_api_key or (project.confidential and not cfg.confidential_allowed):
            raise HTTPException(422, "Provider nicht für dieses Projekt freigegeben")
        model = payload.model_id or (cfg.allowed_models[0] if cfg.allowed_models else None)
        if not model or model not in (cfg.allowed_models or []):
            raise HTTPException(422, "Kein freigegebenes Modell gewählt")
    job = create_job(db, kind="document_prepare", tenant_id=doc.tenant_id, project_id=project_id,
        payload={"document_version_id": str(version.id), "provider_config_id": str(payload.provider_config_id) if payload.provider_config_id else None, "model_id": model, "actor_id": str(actor.user.id)})
    db.commit()
    if get_settings().inline_jobs:
        from kusys.documents.preparation_tasks import process_preparation
        try:
            process_preparation(db, job.id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        from kusys.jobs.tasks import document_prepare_task
        if document_prepare_task is None:
            raise HTTPException(503, "Worker ist nicht verfügbar")
        document_prepare_task.delay(str(job.id))
    return {"job_id": str(job.id), "status": job.status}


@router.get("/projects/{project_id}/document-preparations")
def preparations(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    from kusys.persistence.models import Job
    require_project_access(db, actor, project_id)
    rows = db.scalars(select(Job).where(Job.project_id == project_id, Job.kind == "document_prepare").order_by(Job.created_at.desc()).limit(10))
    return [{"id": str(j.id), "status": j.status, "message": j.message, "result": j.result} for j in rows]
