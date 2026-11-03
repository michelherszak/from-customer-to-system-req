from __future__ import annotations

import uuid
from sqlalchemy import delete
from sqlalchemy.orm import Session

from kusys.artifacts.storage import storage
from kusys.documents.service import DocumentService
from kusys.jobs.service import fail_job, finish_job, start_job, update_job
from kusys.persistence.models import Document, DocumentVersion, ExtractedBlock, Job

service = DocumentService()


def process_document_extract(db: Session, job_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> dict:
    job = db.get(Job, job_id)
    if not job or job.kind != "document_extract":
        raise ValueError("Dokumentjob nicht gefunden")
    if job.status == "succeeded":
        return job.result or {}
    version_id = uuid.UUID(str(job.payload["document_version_id"]))
    version = db.get(DocumentVersion, version_id)
    if not version:
        fail_job(job, "document_version_missing", "Dokumentversion nicht gefunden")
        db.commit()
        raise ValueError("Dokumentversion nicht gefunden")
    document = db.get(Document, version.document_id)
    if not document:
        fail_job(job, "document_missing", "Dokument nicht gefunden")
        db.commit()
        raise ValueError("Dokument nicht gefunden")
    if job.status == "cancel_requested":
        job.status = "cancelled"; job.finished_at = job.updated_at
        db.commit(); return {"cancelled": True}
    try:
        start_job(job, "Dokument wird extrahiert")
        version.status = "extracting"
        db.commit()
        blocks, meta = service.extract(storage.path(version.storage_key))
        db.execute(delete(ExtractedBlock).where(ExtractedBlock.document_version_id == version.id))
        update_job(job, 60, "Extrahierte Blöcke werden gespeichert")
        for block in blocks:
            db.add(
                ExtractedBlock(
                    tenant_id=document.tenant_id,
                    document_version_id=version.id,
                    page_number=block.page_number,
                    block_index=block.block_index,
                    block_type=block.block_type,
                    heading_path=block.heading_path,
                    source_text=block.source_text,
                    normalized_text=block.normalized_text,
                    coordinates=block.coordinates,
                    table_meta=block.table_meta,
                    source_checksum=block.source_checksum,
                    text_source=block.text_source,
                    quality_status=block.quality_status,
                    created_by=actor_id,
                )
            )
        version.status = "ready"
        version.page_count = meta.get("page_count")
        version.extraction_meta = meta
        result = {"document_version_id": str(version.id), "blocks": len(blocks)}
        finish_job(job, result)
        db.commit()
        return result
    except Exception as exc:
        version.status = "failed"
        fail_job(job, "document_extract_failed", type(exc).__name__)
        db.commit()
        raise
