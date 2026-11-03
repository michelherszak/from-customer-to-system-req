from __future__ import annotations

import re
import uuid
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.persistence.models import Document, DocumentVersion, ExtractedBlock, ReviewRevision, Section, SectionRevision

REQ_RE = re.compile(r"\b(muss|soll|shall|must|required|should)\b", re.I)
CONTEXT_RE = re.compile(r"\b(ist|besteht aus|current|existing|today)\b", re.I)


def automatic_category(block: ExtractedBlock) -> tuple[str, str | None]:
    if block.block_type == "heading": return "context", None
    if CONTEXT_RE.search(block.normalized_text) and not REQ_RE.search(block.normalized_text): return "context", None
    if REQ_RE.search(block.normalized_text): return "requirement", None
    return "context", None


def rebuild_review(db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID, actor_id: uuid.UUID, selection: dict[str, str] | None = None) -> ReviewRevision:
    selection = selection or {}
    max_rev = db.scalar(select(func.max(ReviewRevision.revision_no)).where(ReviewRevision.project_id == project_id)) or 0
    review = ReviewRevision(tenant_id=tenant_id, project_id=project_id, revision_no=max_rev + 1, status="draft", source_selection=selection, created_by=actor_id)
    db.add(review); db.flush()
    docs = list(db.scalars(select(Document).where(Document.project_id == project_id, Document.deleted_at.is_(None))))
    order = 0
    for doc in docs:
        selected_id = selection.get(str(doc.id))
        if selected_id:
            version = db.get(DocumentVersion, uuid.UUID(selected_id))
        else:
            version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.status == "ready").order_by(DocumentVersion.version.desc()))
        if not version: continue
        for block in db.scalars(select(ExtractedBlock).where(ExtractedBlock.document_version_id == version.id).order_by(ExtractedBlock.page_number, ExtractedBlock.block_index)):
            cat, note = automatic_category(block)
            db.add(Section(
                tenant_id=tenant_id, review_revision_id=review.id, extracted_block_id=block.id, order_index=order,
                section_type=block.block_type, source_text=block.source_text, normalized_text=block.normalized_text,
                edited_text=block.normalized_text, category=cat, category_source="automatic", review_note=note, created_by=actor_id,
            ))
            order += 1
    return review


def snapshot_section(section: Section) -> dict:
    return {"edited_text": section.edited_text, "category": section.category, "excluded": section.excluded, "deleted_at": section.deleted_at.isoformat() if section.deleted_at else None, "order_index": section.order_index, "section_type": section.section_type, "heading_level": section.heading_level}


def save_section_revision(db: Session, section: Section, actor_id: uuid.UUID) -> None:
    n = db.scalar(select(func.max(SectionRevision.revision_no)).where(SectionRevision.section_id == section.id)) or 0
    db.add(SectionRevision(section_id=section.id, revision_no=n + 1, snapshot=snapshot_section(section), created_by=actor_id))
