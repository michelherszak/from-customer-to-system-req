"""Apply a source-complete preparation to a new review, preserving source-matched edits."""
import uuid
from sqlalchemy import func, select
from kusys.persistence.models import Job, Document, DocumentVersion, ExtractedBlock, ReviewRevision, Section
from kusys.review.service import automatic_category


def create_prepared_review(db, project_id, tenant_id, actor_id, preparation_id, expected_review_id):
    job = db.get(Job, preparation_id)
    if not job or job.kind != "document_prepare" or job.project_id != project_id or job.status != "succeeded":
        raise ValueError("Keine abgeschlossene Aufbereitung dieses Projekts")
    previous = db.scalar(select(ReviewRevision).where(ReviewRevision.project_id == project_id).order_by(ReviewRevision.revision_no.desc()))
    if (previous.id if previous else None) != expected_review_id:
        raise ValueError("Prüfschritt wurde inzwischen geändert; bitte Vorschau neu laden")
    result = job.result
    version = db.get(DocumentVersion, uuid.UUID(result["document_version_id"]))
    doc = db.get(Document, version.document_id) if version else None
    if not doc or doc.deleted_at or version.sha256 != result["source_sha256"]:
        raise ValueError("Dokumentquelle ist nicht mehr verfügbar")
    latest = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.status == "ready").order_by(DocumentVersion.version.desc()))
    if not latest or latest.id != version.id:
        raise ValueError("Neuere Dokumentversion vorhanden; bitte erneut aufbereiten")
    blocks = {str(x.id): x for x in db.scalars(select(ExtractedBlock).where(ExtractedBlock.document_version_id == version.id))}
    from kusys.documents.preparation import validate_and_materialize
    originals = result["original_blocks"]
    for item in originals:
        if item["id"] not in blocks or item["text"] != blocks[item["id"]].source_text:
            raise ValueError("Quellblöcke wurden seit der Aufbereitung verändert")
    groups = validate_and_materialize(originals, {"groups": [{key: x[key] for key in ("source_ids", "kind", "reason", "uncertain")} for x in result["groups"]]})
    existing = list(db.scalars(select(Section).where(Section.review_revision_id == previous.id).order_by(Section.order_index))) if previous else []
    by_block = {}
    for section in existing:
        if section.extracted_block_id:
            by_block.setdefault(str(section.extracted_block_id), []).append(section)
    # Resolve earlier grouped sections back to all their source IDs before preserving edits.
    previous_job_id = (previous.source_selection or {}).get("__preparation_job_id") if previous else None
    previous_job = db.get(Job, uuid.UUID(previous_job_id)) if previous_job_id else None
    if previous_job and previous_job.result:
        for group in previous_job.result.get("groups", []):
            for old in existing:
                if str(old.extracted_block_id) == group["source_ids"][0] and old.source_text == group["text"]:
                    for sid in group["source_ids"]:
                        if old not in by_block.setdefault(sid, []): by_block[sid].append(old)
    revision_no = (db.scalar(select(func.max(ReviewRevision.revision_no)).where(ReviewRevision.project_id == project_id)) or 0) + 1
    review = ReviewRevision(project_id=project_id, tenant_id=tenant_id, revision_no=revision_no, status="draft",
        source_selection={**(previous.source_selection or {} if previous else {}), str(doc.id): str(version.id), "__preparation_job_id": str(job.id)}, created_by=actor_id)
    db.add(review); db.flush()
    order = 0
    copied = set()
    def copy_section(old):
        nonlocal order
        if old.id in copied:
            return
        copied.add(old.id)
        db.add(Section(tenant_id=tenant_id, review_revision_id=review.id, extracted_block_id=old.extracted_block_id,
            order_index=order, section_type=old.section_type, heading_level=old.heading_level,
            source_text=old.source_text, normalized_text=old.normalized_text, edited_text=old.edited_text,
            category=old.category, category_source=old.category_source, excluded=old.excluded, manual=old.manual,
            review_note=old.review_note, deleted_at=old.deleted_at, deleted_by=old.deleted_by, delete_reason=old.delete_reason, created_by=actor_id))
        order += 1
    for group in groups:
        old_sections = [s for sid in group["source_ids"] for s in by_block.get(sid, [])]
        protected = any(s.category_source == "manual" or s.manual or s.excluded or s.deleted_at or s.edited_text != s.normalized_text for s in old_sections)
        if protected:
            # Do not merge across a manual correction or restore excluded/deleted material.
            for sid in group["source_ids"]:
                if sid in by_block:
                    for old in by_block[sid]: copy_section(old)
                else:
                    block = blocks[sid]; category, note = automatic_category(block)
                    db.add(Section(tenant_id=tenant_id, review_revision_id=review.id, extracted_block_id=block.id, order_index=order, section_type=block.block_type, source_text=block.source_text, normalized_text=block.normalized_text, edited_text=block.normalized_text, category=category, category_source="automatic", review_note=note, created_by=actor_id)); order += 1
            continue
        block = blocks[group["source_ids"][0]]
        from types import SimpleNamespace
        from kusys.documents.service import normalize_text
        category, _ = automatic_category(SimpleNamespace(block_type=group["kind"], normalized_text=normalize_text(group["text"])))
        from kusys.documents.preparation import REQ_ID
        if (REQ_ID.match(group["text"].strip()) and len(group["text"].split()) > 8) or any(automatic_category(blocks[sid])[0] == "requirement" for sid in group["source_ids"]): category = "requirement"
        text = group["text"]
        from kusys.documents.service import normalize_text
        db.add(Section(tenant_id=tenant_id, review_revision_id=review.id, extracted_block_id=block.id,
            order_index=order, section_type=group["kind"], source_text=text, normalized_text=normalize_text(text), edited_text=normalize_text(text),
            category=category, category_source="automatic", review_note=("Bitte Gruppierung prüfen. " if group["uncertain"] else "") + group["reason"], created_by=actor_id))
        order += 1
    # Keep other documents and manual additions from the previous review unchanged.
    for old in existing:
        if not old.extracted_block_id or str(old.extracted_block_id) not in blocks:
            copy_section(old)
    return review
