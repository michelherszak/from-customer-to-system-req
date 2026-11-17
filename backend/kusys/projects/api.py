from __future__ import annotations

import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access, require_tenant_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.security import utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import Project, ProjectMembership, TenantMembership, Tenant, Customer, User

router = APIRouter(tags=["projects"])

class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    tenant_id: uuid.UUID
    project_number: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)
    short_description: str | None = None
    customer_id: uuid.UUID | None = None
    customer_contact: str | None = None
    confidential: bool = False
    document_language: str = "de"
    planned_start: date | None = None

class ProjectUpdate(BaseModel):
    expected_version: int
    name: str | None = None
    short_description: str | None = None
    customer_id: uuid.UUID | None = None
    customer_contact: str | None = None
    status: str | None = None
    confidential: bool | None = None
    document_language: str | None = None
    planned_start: date | None = None

class MemberCreate(BaseModel):
    user_id: uuid.UUID
    role: str


def serialize(p: Project) -> dict:
    return {
        "id": str(p.id), "tenant_id": str(p.tenant_id), "project_number": p.project_number, "name": p.name,
        "short_description": p.short_description, "customer_id": str(p.customer_id) if p.customer_id else None,
        "customer_contact": p.customer_contact, "status": p.status, "confidential": p.confidential,
        "document_language": p.document_language, "planned_start": p.planned_start, "lock_version": p.lock_version,
    }

@router.get("/projects")
def list_projects(db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    tenant_ids = [x.tenant_id for x in db.scalars(select(TenantMembership).where(TenantMembership.user_id == actor.user.id, TenantMembership.role == "company_admin"))]
    project_ids = [x.project_id for x in db.scalars(select(ProjectMembership).where(ProjectMembership.user_id == actor.user.id, ProjectMembership.role.in_(["project_lead", "project_member"]))) ]
    query = select(Project).where(Project.deleted_at.is_(None))
    if actor.user.is_platform_admin and not tenant_ids and not project_ids:
        return []
    if tenant_ids or project_ids:
        query = query.where((Project.tenant_id.in_(tenant_ids)) | (Project.id.in_(project_ids)))
    else:
        return []
    return [serialize(x) for x in db.scalars(query.order_by(Project.project_number))]

def creation_tenant_ids(db: Session, actor: Actor) -> set:
    admins = db.scalars(select(TenantMembership.tenant_id).where(TenantMembership.user_id == actor.user.id, TenantMembership.role == "company_admin"))
    leads = db.scalars(select(Project.tenant_id).join(ProjectMembership, ProjectMembership.project_id == Project.id).where(ProjectMembership.user_id == actor.user.id, ProjectMembership.role == "project_lead"))
    return set(admins) | set(leads)


@router.get("/project-creation-options")
def creation_options(db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    ids = creation_tenant_ids(db, actor)
    return [{"id": str(t.id), "name": t.name} for t in db.scalars(select(Tenant).where(Tenant.id.in_(ids)).order_by(Tenant.name))]


@router.post("/projects")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    if payload.tenant_id not in creation_tenant_ids(db, actor):
        raise HTTPException(403, "Nur Firmen-Admin oder Projektleitung dürfen Projekte in dieser Firma erstellen")
    if payload.customer_id:
        customer = db.get(Customer, payload.customer_id)
        if not customer or customer.tenant_id != payload.tenant_id or customer.deleted_at:
            raise HTTPException(422, "Kunde gehört nicht zu dieser Firma")
    p = Project(**payload.model_dump(), owner_user_id=actor.user.id, created_by=actor.user.id)
    try:
        db.add(p); db.flush()
        db.add(ProjectMembership(project_id=p.id, user_id=actor.user.id, role="project_lead", created_by=actor.user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Projektnummer ist in dieser Firma bereits vergeben, auch bei gelöschten Projekten") from None
    db.refresh(p)
    return serialize(p)

@router.get("/projects/{project_id}")
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    p = db.get(Project, project_id)
    if not p or p.deleted_at: raise HTTPException(404, "Projekt nicht gefunden")
    return serialize(p)

@router.patch("/projects/{project_id}")
def update_project(project_id: uuid.UUID, payload: ProjectUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    p = db.get(Project, project_id)
    if not p or p.deleted_at: raise HTTPException(404, "Projekt nicht gefunden")
    check_expected_version(p, payload.expected_version)
    if payload.status is not None and payload.status not in {"active", "inactive"}:
        raise HTTPException(422, "Projektstatus muss active oder inactive sein")
    for k, v in payload.model_dump(exclude={"expected_version"}, exclude_none=True).items(): setattr(p, k, v)
    bump_version(p); db.commit(); db.refresh(p)
    return serialize(p)

@router.delete("/projects/{project_id}")
def delete_project(project_id: uuid.UUID, reason: str, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    p = db.get(Project, project_id)
    if not p or p.deleted_at: raise HTTPException(404, "Projekt nicht gefunden")
    reason = reason.strip()
    if not reason or len(reason) > 500: raise HTTPException(422, "Löschgrund muss 1 bis 500 Zeichen enthalten")
    p.deleted_at = utcnow(); p.deleted_by = actor.user.id; p.delete_reason = reason; bump_version(p)
    db.commit(); return {"ok": True}

def member_data(membership, user):
    return {"id":str(membership.id),"user_id":str(membership.user_id),"role":membership.role,
        "display_name":user.display_name if user else "Gelöschter Benutzer", "username":user.username if user else "", "active":bool(user and user.active and not user.deleted_at)}


@router.get("/projects/{project_id}/members")
def list_members(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    rows=db.execute(select(ProjectMembership,User).outerjoin(User,User.id==ProjectMembership.user_id).where(ProjectMembership.project_id==project_id).order_by(User.display_name)).all()
    return [member_data(membership,user) for membership,user in rows]


@router.get("/projects/{project_id}/member-candidates")
def member_candidates(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"})
    project=db.get(Project,project_id)
    if not project or project.deleted_at:raise HTTPException(404,"Projekt nicht gefunden")
    assigned=select(ProjectMembership.user_id).where(ProjectMembership.project_id==project_id)
    rows=db.execute(select(User,TenantMembership.role).join(TenantMembership,TenantMembership.user_id==User.id).where(TenantMembership.tenant_id==project.tenant_id,TenantMembership.role.in_(["project_lead","project_member","customer"]),User.active.is_(True),User.deleted_at.is_(None),User.id.not_in(assigned)).order_by(User.display_name)).all()
    return [{"id":str(user.id),"display_name":user.display_name,"username":user.username,"tenant_role":role,"default_role":"customer" if role=="customer" else "project_member"} for user,role in rows]


@router.post("/projects/{project_id}/members")
def add_member(project_id: uuid.UUID, payload: MemberCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"})
    project=db.scalar(select(Project).where(Project.id==project_id).with_for_update())
    if not project or project.deleted_at:raise HTTPException(404,"Projekt nicht gefunden")
    if payload.role not in {"project_lead","project_member","customer"}:raise HTTPException(422,"Ungültige Projektrolle")
    user=db.get(User,payload.user_id)
    company_role=db.scalar(select(TenantMembership.role).where(TenantMembership.tenant_id==project.tenant_id,TenantMembership.user_id==payload.user_id))
    if not user or not user.active or user.deleted_at or not company_role:raise HTTPException(422,"Person ist kein aktives Mitglied dieser Firma")
    existing=db.scalar(select(ProjectMembership).where(ProjectMembership.project_id==project_id,ProjectMembership.user_id==payload.user_id))
    if existing:
        if existing.role!=payload.role:raise HTTPException(409,"Person ist bereits mit einer anderen Projektrolle zugeordnet")
        return member_data(existing,user)
    if company_role=="company_admin":raise HTTPException(409,"Firmen-Admins haben bereits automatisch Zugriff")
    if company_role not in {"project_lead","project_member","customer"} or (company_role=="customer") != (payload.role=="customer"):
        raise HTTPException(422,"Kunden dürfen nur als Kunden, interne Personen nur als Projektmitglieder oder Projektleitung hinzugefügt werden")
    membership=ProjectMembership(project_id=project_id,user_id=payload.user_id,role=payload.role,created_by=actor.user.id)
    db.add(membership);db.commit();db.refresh(membership)
    return member_data(membership,user)


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(project_id: uuid.UUID, user_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"})
    project=db.scalar(select(Project).where(Project.id==project_id).with_for_update())
    if not project or project.deleted_at:raise HTTPException(404,"Projekt nicht gefunden")
    membership=db.scalar(select(ProjectMembership).where(ProjectMembership.project_id==project_id,ProjectMembership.user_id==user_id))
    if not membership:raise HTTPException(404,"Projektzuordnung nicht gefunden")
    if membership.role=="project_lead":
        other=db.scalar(select(ProjectMembership.id).join(User,User.id==ProjectMembership.user_id).where(ProjectMembership.project_id==project_id,ProjectMembership.user_id!=user_id,ProjectMembership.role=="project_lead",User.active.is_(True),User.deleted_at.is_(None)).limit(1))
        if not other:raise HTTPException(409,"Die letzte aktive Projektleitung kann nicht entfernt werden")
    db.delete(membership);db.commit()
    return {"ok":True}


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    p=db.get(Project,project_id)
    if not p:raise HTTPException(404,"Projekt nicht gefunden")
    require_tenant_access(db,actor,p.tenant_id,{"company_admin"})
    p.deleted_at=None;p.deleted_by=None;p.delete_reason=None;bump_version(p);db.commit();db.refresh(p);return serialize(p)
