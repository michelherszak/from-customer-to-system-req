from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.security import utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import Project, ReviewRevision, Section
from kusys.review.service import rebuild_review, save_section_revision

router = APIRouter(tags=["review"])

class RebuildRequest(BaseModel):
    source_selection: dict[str, str] = {}

class SectionUpdate(BaseModel):
    expected_version: int
    edited_text: str | None = None
    category: str | None = None
    excluded: bool | None = None
    section_type: str | None = None
    heading_level: int | None = None
    order_index: int | None = None

class ManualSection(BaseModel):
    text: str
    category: str = "requirement"
    section_type: str = "paragraph"


def serialize_review(r: ReviewRevision) -> dict:
    return {"id": str(r.id), "project_id": str(r.project_id), "revision_no": r.revision_no, "status": r.status, "approved_at": r.approved_at, "lock_version": r.lock_version, "source_selection": r.source_selection}


def serialize_section(s: Section) -> dict:
    return {"id": str(s.id), "order_index": s.order_index, "section_type": s.section_type, "heading_level": s.heading_level, "source_text": s.source_text, "normalized_text": s.normalized_text, "edited_text": s.edited_text, "category": s.category, "category_source": s.category_source, "excluded": s.excluded, "manual": s.manual, "deleted": s.deleted_at is not None, "lock_version": s.lock_version, "review_note": s.review_note}

@router.get("/projects/{project_id}/review")
def get_review(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    r = db.scalar(select(ReviewRevision).where(ReviewRevision.project_id == project_id).order_by(ReviewRevision.revision_no.desc()))
    if not r: return {"review": None, "sections": []}
    sections = list(db.scalars(select(Section).where(Section.review_revision_id == r.id).order_by(Section.order_index)))
    return {"review": serialize_review(r), "sections": [serialize_section(s) for s in sections]}

@router.post("/projects/{project_id}/review/rebuild")
def rebuild(project_id: uuid.UUID, payload: RebuildRequest, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin"})
    p = db.get(Project, project_id)
    r = rebuild_review(db, project_id, p.tenant_id, actor.user.id, payload.source_selection)
    db.commit(); db.refresh(r)
    return serialize_review(r)

@router.patch("/review-revisions/{review_id}/sections/{section_id}")
def update_section(review_id: uuid.UUID, section_id: uuid.UUID, payload: SectionUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r = db.get(ReviewRevision, review_id)
    if not r: raise HTTPException(404, "Prüfschrittrevision nicht gefunden")
    require_project_access(db, actor, r.project_id, {"project_lead", "project_member", "company_admin"})
    s = db.get(Section, section_id)
    if not s or s.review_revision_id != review_id: raise HTTPException(404, "Abschnitt nicht gefunden")
    check_expected_version(s, payload.expected_version); save_section_revision(db, s, actor.user.id)
    for k, v in payload.model_dump(exclude={"expected_version"}, exclude_none=True).items(): setattr(s, k, v)
    if payload.category is not None: s.category_source = "manual"
    bump_version(s)
    if r.status == "approved": r.status = "draft"; r.approved_at = None; r.approved_by = None; bump_version(r)
    db.commit(); db.refresh(s)
    return serialize_section(s)

@router.post("/review-revisions/{review_id}/sections")
def add_section(review_id: uuid.UUID, payload: ManualSection, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r = db.get(ReviewRevision, review_id)
    if not r: raise HTTPException(404, "Prüfschrittrevision nicht gefunden")
    require_project_access(db, actor, r.project_id, {"project_lead", "project_member", "company_admin"})
    max_order = max((x.order_index for x in db.scalars(select(Section).where(Section.review_revision_id == review_id))), default=-1)
    s = Section(tenant_id=r.tenant_id, review_revision_id=r.id, order_index=max_order + 1, section_type=payload.section_type, source_text=payload.text, normalized_text=payload.text, edited_text=payload.text, category=payload.category, category_source="manual", manual=True, created_by=actor.user.id)
    db.add(s); r.status = "draft"; r.approved_at = None; r.approved_by = None; db.commit(); db.refresh(s)
    return serialize_section(s)

@router.post("/review-revisions/{review_id}/approve")
def approve(review_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r = db.get(ReviewRevision, review_id)
    if not r: raise HTTPException(404, "Prüfschrittrevision nicht gefunden")
    require_project_access(db, actor, r.project_id, {"project_lead", "company_admin"})
    active_requirements = db.scalar(select(Section).where(Section.review_revision_id == review_id, Section.category == "requirement", Section.excluded.is_(False), Section.deleted_at.is_(None)).limit(1))
    if not active_requirements: raise HTTPException(422, "Mindestens ein aktiver Anforderungsabschnitt ist erforderlich")
    r.status = "approved"; r.approved_at = utcnow(); r.approved_by = actor.user.id; bump_version(r); db.commit(); db.refresh(r)
    return serialize_review(r)

class SectionSplit(BaseModel):
    expected_version: int
    parts: list[str] = []

class SectionMerge(BaseModel):
    expected_version: int
    other_section_id: uuid.UUID

@router.post("/review-revisions/{review_id}/sections/{section_id}/split")
def split_section(review_id: uuid.UUID, section_id: uuid.UUID, payload: SectionSplit, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r = db.get(ReviewRevision, review_id)
    s = db.get(Section, section_id)
    if not r or not s or s.review_revision_id != review_id or s.deleted_at is not None:
        raise HTTPException(404, "Abschnitt nicht gefunden")
    require_project_access(db, actor, r.project_id, {"project_lead", "project_member", "company_admin"})
    check_expected_version(s, payload.expected_version)
    parts = [x.strip() for x in payload.parts if x.strip()]
    if len(parts) < 2:
        raise HTTPException(422, "Mindestens zwei nicht-leere Teile sind erforderlich")
    save_section_revision(db, s, actor.user.id)
    s.edited_text = parts[0]; s.normalized_text = parts[0]; bump_version(s)
    following = list(db.scalars(select(Section).where(Section.review_revision_id == review_id, Section.order_index > s.order_index).order_by(Section.order_index.desc())))
    shift = len(parts) - 1
    for row in following:
        row.order_index += shift
    created=[]
    for i, text in enumerate(parts[1:], start=1):
        child = Section(
            tenant_id=r.tenant_id, review_revision_id=r.id, order_index=s.order_index + i,
            section_type=s.section_type, heading_level=s.heading_level, source_text=s.source_text,
            normalized_text=text, edited_text=text, category=s.category, category_source="manual",
            excluded=s.excluded, manual=True, review_note="Aus Teilung erzeugt", created_by=actor.user.id,
        )
        db.add(child); db.flush(); created.append(child)
    r.status="draft"; r.approved_at=None; r.approved_by=None; bump_version(r)
    db.commit()
    return {"source": serialize_section(s), "parts": [serialize_section(x) for x in created]}

@router.post("/review-revisions/{review_id}/sections/{section_id}/merge")
def merge_section(review_id: uuid.UUID, section_id: uuid.UUID, payload: SectionMerge, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r=db.get(ReviewRevision,review_id); a=db.get(Section,section_id); b=db.get(Section,payload.other_section_id)
    if not r or not a or not b or a.review_revision_id!=review_id or b.review_revision_id!=review_id or a.deleted_at or b.deleted_at:
        raise HTTPException(404,"Abschnitt nicht gefunden")
    require_project_access(db,actor,r.project_id,{"project_lead","project_member","company_admin"});check_expected_version(a,payload.expected_version)
    first,second=(a,b) if a.order_index<=b.order_index else (b,a)
    if second.order_index-first.order_index!=1:raise HTTPException(422,"Nur benachbarte Abschnitte können zusammengeführt werden")
    save_section_revision(db,first,actor.user.id);save_section_revision(db,second,actor.user.id)
    text="\n".join(x for x in [first.edited_text or first.normalized_text,second.edited_text or second.normalized_text] if x)
    first.edited_text=text;first.normalized_text=text;first.category_source="manual";bump_version(first)
    second.deleted_at=utcnow();second.deleted_by=actor.user.id;second.delete_reason="Zusammengeführt";bump_version(second)
    for row in db.scalars(select(Section).where(Section.review_revision_id==review_id,Section.order_index>second.order_index)):
        row.order_index-=1
    r.status="draft";r.approved_at=None;r.approved_by=None;bump_version(r);db.commit()
    return serialize_section(first)

@router.delete("/review-revisions/{review_id}/sections/{section_id}")
def delete_section(review_id: uuid.UUID, section_id: uuid.UUID, reason: str, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r=db.get(ReviewRevision,review_id);s=db.get(Section,section_id)
    if not r or not s or s.review_revision_id!=review_id or s.deleted_at:raise HTTPException(404,"Abschnitt nicht gefunden")
    require_project_access(db,actor,r.project_id,{"project_lead","project_member","company_admin"})
    if not reason.strip():raise HTTPException(422,"Löschgrund ist erforderlich")
    save_section_revision(db,s,actor.user.id);s.deleted_at=utcnow();s.deleted_by=actor.user.id;s.delete_reason=reason;bump_version(s)
    r.status="draft";r.approved_at=None;r.approved_by=None;bump_version(r);db.commit();return {"status":"deleted"}

@router.post("/review-revisions/{review_id}/sections/{section_id}/restore")
def restore_section(review_id: uuid.UUID, section_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r=db.get(ReviewRevision,review_id);s=db.get(Section,section_id)
    if not r or not s or s.review_revision_id!=review_id:raise HTTPException(404,"Abschnitt nicht gefunden")
    require_project_access(db,actor,r.project_id,{"project_lead","project_member","company_admin"})
    s.deleted_at=None;s.deleted_by=None;s.delete_reason=None;bump_version(s);r.status="draft";r.approved_at=None;r.approved_by=None;bump_version(r);db.commit();return serialize_section(s)
