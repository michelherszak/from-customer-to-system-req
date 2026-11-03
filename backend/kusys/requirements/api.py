from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.analysis.impact import ImpactAnalysisService
from kusys.analysis.service import requirement_snapshot
from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.security import utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import (
    ClarificationItem, Project, Requirement, RequirementRelation, RequirementRevision,
    WorkPackageRequirement, Offer, OfferScopeItem, OfferVersion, MaterialItem,
)
from kusys.services.calculation import load_calculation_inputs

router = APIRouter(tags=["requirements"])
RELATION_TYPES = {"requires", "enables", "conflicts_with", "related_to", "replaces", "split_from"}

class RequirementCreate(BaseModel):
    title: str
    text: str
    priority: str = "soll"
    budget_eur: Decimal | None = None
    max_price_eur: Decimal | None = None
    budget_source: str | None = "manual"

class RequirementUpdate(BaseModel):
    expected_version: int
    title: str | None = None
    text: str | None = None
    priority: str | None = None
    budget_eur: Decimal | None = None
    max_price_eur: Decimal | None = None
    budget_source: str | None = None

class RelationCreate(BaseModel):
    target_id: uuid.UUID
    relation_type: str
    rationale: str | None = None
    origin: str = "manual"

class SplitRequest(BaseModel):
    expected_version: int
    parts: list[RequirementCreate] = Field(min_length=2)

class ClarificationCreate(BaseModel):
    text: str
    requirement_ids: list[uuid.UUID] = []
    origin: str = "manual"

class ClarificationUpdate(BaseModel):
    expected_version: int
    text: str | None = None
    status: str | None = None


def serialize(r: Requirement) -> dict:
    return {
        "id": str(r.id), "project_id": str(r.project_id), "key": r.key, "title": r.title, "text": r.text,
        "priority": r.priority, "origin": r.origin, "business_revision": r.business_revision,
        "budget_eur": str(r.budget_eur) if r.budget_eur is not None else None,
        "max_price_eur": str(r.max_price_eur) if r.max_price_eur is not None else None,
        "budget_source": r.budget_source, "source_refs": r.source_refs, "lock_version": r.lock_version,
        "replacement_status": r.replacement_status,
    }


def save_revision(db: Session, r: Requirement, actor_id: uuid.UUID) -> None:
    db.add(RequirementRevision(requirement_id=r.id, revision_no=r.business_revision, snapshot=requirement_snapshot(r), created_by=actor_id))

@router.get("/projects/{project_id}/requirements")
def list_requirements(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    reqs = list(db.scalars(select(Requirement).where(Requirement.project_id == project_id, Requirement.deleted_at.is_(None)).order_by(Requirement.key)))
    links = list(db.scalars(select(RequirementRelation).where(RequirementRelation.project_id == project_id, RequirementRelation.active.is_(True))))
    rel_by_source: dict[uuid.UUID, list] = {}
    for x in links:
        rel_by_source.setdefault(x.source_id, []).append({"id": str(x.id), "target_id": str(x.target_id), "relation_type": x.relation_type, "rationale": x.rationale, "origin": x.origin})
    return [{**serialize(r), "relations": rel_by_source.get(r.id, [])} for r in reqs]

@router.post("/projects/{project_id}/requirements")
def create_requirement(project_id: uuid.UUID, payload: RequirementCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin"})
    project = db.get(Project, project_id)
    max_no = 0
    for key in db.scalars(select(Requirement.key).where(Requirement.project_id == project_id)):
        try: max_no=max(max_no,int(key.split("-")[-1]))
        except: pass
    r = Requirement(tenant_id=project.tenant_id, project_id=project_id, key=f"REQ-{max_no+1:04d}", origin="manual", created_by=actor.user.id, **payload.model_dump())
    db.add(r); db.flush(); save_revision(db, r, actor.user.id); db.commit(); db.refresh(r)
    return serialize(r)

@router.patch("/requirements/{requirement_id}")
def update_requirement(requirement_id: uuid.UUID, payload: RequirementUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r = db.get(Requirement, requirement_id)
    if not r or r.deleted_at: raise HTTPException(404, "Anforderung nicht gefunden")
    require_project_access(db, actor, r.project_id, {"project_lead", "project_member", "company_admin"})
    check_expected_version(r, payload.expected_version)
    for k, v in payload.model_dump(exclude={"expected_version"}, exclude_unset=True).items(): setattr(r, k, v)
    r.business_revision += 1; bump_version(r); save_revision(db, r, actor.user.id); db.commit(); db.refresh(r)
    return serialize(r)

@router.post("/requirements/{requirement_id}/relations")
def add_relation(requirement_id: uuid.UUID, payload: RelationCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    source = db.get(Requirement, requirement_id); target = db.get(Requirement, payload.target_id)
    if not source or not target or source.project_id != target.project_id: raise HTTPException(404, "Anforderung nicht gefunden")
    require_project_access(db, actor, source.project_id, {"project_lead", "project_member", "company_admin"})
    if payload.relation_type not in RELATION_TYPES: raise HTTPException(422, "Unbekannter Beziehungstyp")
    if source.id == target.id: raise HTTPException(422, "Selbstbeziehung ist nicht zulässig")
    rel = RequirementRelation(tenant_id=source.tenant_id, project_id=source.project_id, source_id=source.id, target_id=target.id, relation_type=payload.relation_type, rationale=payload.rationale, origin=payload.origin, created_by=actor.user.id)
    db.add(rel); db.commit()
    return {"id": str(rel.id), "source_id": str(rel.source_id), "target_id": str(rel.target_id), "relation_type": rel.relation_type}

def _affected_offer_variants(db: Session, project_id: uuid.UUID, requirement_ids: set[uuid.UUID]) -> list[dict]:
    out=[]
    for offer in db.scalars(select(Offer).where(Offer.project_id==project_id,Offer.deleted_at.is_(None))):
        for version in db.scalars(select(OfferVersion).where(OfferVersion.offer_id==offer.id)):
            hit=db.scalar(select(OfferScopeItem.id).where(OfferScopeItem.offer_version_id==version.id,OfferScopeItem.requirement_id.in_(requirement_ids),OfferScopeItem.included.is_(True)).limit(1))
            if hit:out.append({"offer_id":str(offer.id),"offer_number":offer.offer_number,"variant_name":offer.variant_name,"version_id":str(version.id),"version":version.version,"status":version.status,"immutable":version.status not in {"Entwurf","zur Freigabe"}})
    return out

@router.get("/requirements/{requirement_id}/impact")
def impact(requirement_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    r = db.get(Requirement, requirement_id)
    if not r or r.deleted_at: raise HTTPException(404, "Anforderung nicht gefunden")
    require_project_access(db, actor, r.project_id)
    project, graph, wps, priced, rates, capacities, materials, budgets, start, holidays, hours_per_day, weekdays = load_calculation_inputs(db, r.project_id)
    result = ImpactAnalysisService().simulate_requirement_removal(str(r.id), graph, wps, priced, rates, capacities, materials, budgets, start, holidays, hours_per_day, weekdays)
    return {
        "requirement_id": str(r.id), "dependent_requirement_ids": list(result.dependent_requirement_ids),
        "affected_work_package_ids": list(result.affected_work_package_ids), "affected_material_item_ids": list(result.affected_material_item_ids),
        "hours_delta": result.hours_delta, "cost_delta_eur": str(result.cost_delta_eur),
        "net_delta_eur": str(result.net_delta_eur), "gross_delta_eur": str(result.gross_delta_eur),
        "margin_delta_eur": str(result.margin_delta_eur), "budget_delta_eur": str(result.budget_delta_eur),
        "finish_delta_days": result.finish_delta_days, "critical_path_before": list(result.critical_path_before), "critical_path_after": list(result.critical_path_after),
        "affected_offer_variants": _affected_offer_variants(db,r.project_id,{r.id,*[uuid.UUID(x) for x in result.dependent_requirement_ids]}),
    }

@router.delete("/requirements/{requirement_id}")
def delete_requirement(requirement_id: uuid.UUID, reason: str, confirm: bool = False, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r = db.get(Requirement, requirement_id)
    if not r or r.deleted_at: raise HTTPException(404, "Anforderung nicht gefunden")
    require_project_access(db, actor, r.project_id, {"project_lead", "company_admin"})
    if not confirm:
        raise HTTPException(409, detail={"code": "impact_confirmation_required", "impact_endpoint": f"/api/v1/requirements/{r.id}/impact"})
    if not reason.strip(): raise HTTPException(422, "Löschgrund ist erforderlich")
    r.deleted_at=utcnow(); r.deleted_by=actor.user.id; r.delete_reason=reason; bump_version(r); db.commit()
    return {"ok": True}

@router.post("/requirements/{requirement_id}/split")
def split_requirement(requirement_id: uuid.UUID, payload: SplitRequest, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    source = db.get(Requirement, requirement_id)
    if not source or source.deleted_at: raise HTTPException(404, "Anforderung nicht gefunden")
    require_project_access(db, actor, source.project_id, {"project_lead", "project_member", "company_admin"})
    check_expected_version(source, payload.expected_version)
    source.replacement_status = "abgelöst durch Teilung"; source.business_revision += 1; bump_version(source); save_revision(db, source, actor.user.id)
    max_no=0
    for key in db.scalars(select(Requirement.key).where(Requirement.project_id == source.project_id)):
        try: max_no=max(max_no,int(key.split("-")[-1]))
        except: pass
    created=[]
    for part in payload.parts:
        max_no += 1
        new = Requirement(tenant_id=source.tenant_id, project_id=source.project_id, key=f"REQ-{max_no:04d}", origin="manual", source_refs=source.source_refs, created_by=actor.user.id, **part.model_dump())
        db.add(new); db.flush(); save_revision(db, new, actor.user.id)
        db.add(RequirementRelation(tenant_id=source.tenant_id, project_id=source.project_id, source_id=new.id, target_id=source.id, relation_type="split_from", origin="manual", created_by=actor.user.id))
        created.append(new)
    db.commit()
    return {"source": serialize(source), "parts": [serialize(x) for x in created], "work_package_links_preserved": False}

@router.get("/requirements/{requirement_id}/revisions")
def revisions(requirement_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    r = db.get(Requirement, requirement_id)
    if not r: raise HTTPException(404, "Anforderung nicht gefunden")
    require_project_access(db, actor, r.project_id)
    return [{"revision_no": x.revision_no, "snapshot": x.snapshot, "created_at": x.created_at} for x in db.scalars(select(RequirementRevision).where(RequirementRevision.requirement_id == requirement_id).order_by(RequirementRevision.revision_no))]

@router.get("/projects/{project_id}/clarifications")
def clarifications(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    return [{"id": str(x.id), "key": x.key, "text": x.text, "origin": x.origin, "status": x.status, "requirement_ids": x.requirement_ids, "lock_version": x.lock_version} for x in db.scalars(select(ClarificationItem).where(ClarificationItem.project_id == project_id, ClarificationItem.deleted_at.is_(None)).order_by(ClarificationItem.key))]

@router.post("/projects/{project_id}/clarifications")
def create_clarification(project_id: uuid.UUID, payload: ClarificationCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin", "customer"})
    p=db.get(Project,project_id); n=(db.scalar(select(func.count(ClarificationItem.id)).where(ClarificationItem.project_id==project_id)) or 0)+1
    status="beantwortet – interne Prüfung ausstehend" if payload.origin=="customer" else "offen"
    x=ClarificationItem(tenant_id=p.tenant_id, project_id=project_id, key=f"CLR-{n:04d}", text=payload.text, origin=payload.origin, status=status, requirement_ids=[str(v) for v in payload.requirement_ids], created_by=actor.user.id)
    db.add(x); db.commit(); return {"id":str(x.id),"key":x.key,"status":x.status}

@router.post("/requirements/{requirement_id}/restore")
def restore_requirement(requirement_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    r=db.get(Requirement,requirement_id)
    if not r:raise HTTPException(404,"Anforderung nicht gefunden")
    require_project_access(db,actor,r.project_id,{"project_lead","company_admin"})
    r.deleted_at=None;r.deleted_by=None;r.delete_reason=None;bump_version(r);db.commit();db.refresh(r);return serialize(r)

@router.patch("/clarifications/{clarification_id}")
def update_clarification(clarification_id: uuid.UUID,payload:ClarificationUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    c=db.get(ClarificationItem,clarification_id)
    if not c or c.deleted_at:raise HTTPException(404,"Klärungspunkt nicht gefunden")
    require_project_access(db,actor,c.project_id,{"project_lead","project_member","company_admin"});check_expected_version(c,payload.expected_version)
    for k,v in payload.model_dump(exclude={"expected_version"},exclude_unset=True).items():setattr(c,k,v)
    bump_version(c);db.commit();return {"id":str(c.id),"key":c.key,"text":c.text,"status":c.status,"lock_version":c.lock_version}
