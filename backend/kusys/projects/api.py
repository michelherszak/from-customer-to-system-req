from __future__ import annotations

import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access, require_tenant_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.security import utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import Project, ProjectMembership, TenantMembership

router = APIRouter(tags=["projects"])

class ProjectCreate(BaseModel):
    tenant_id: uuid.UUID
    project_number: str
    name: str
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
    tenant_ids = [x.tenant_id for x in db.scalars(select(TenantMembership).where(TenantMembership.user_id == actor.user.id))]
    project_ids = [x.project_id for x in db.scalars(select(ProjectMembership).where(ProjectMembership.user_id == actor.user.id))]
    query = select(Project).where(Project.deleted_at.is_(None))
    if actor.user.is_platform_admin and not tenant_ids and not project_ids:
        return []
    if tenant_ids or project_ids:
        query = query.where((Project.tenant_id.in_(tenant_ids)) | (Project.id.in_(project_ids)))
    else:
        return []
    return [serialize(x) for x in db.scalars(query.order_by(Project.project_number))]

@router.post("/projects")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_tenant_access(db, actor, payload.tenant_id, {"company_admin"})
    p = Project(**payload.model_dump(), owner_user_id=actor.user.id, created_by=actor.user.id)
    db.add(p); db.flush()
    db.add(ProjectMembership(project_id=p.id, user_id=actor.user.id, role="project_lead", created_by=actor.user.id))
    db.commit(); db.refresh(p)
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
    for k, v in payload.model_dump(exclude={"expected_version"}, exclude_none=True).items(): setattr(p, k, v)
    bump_version(p); db.commit(); db.refresh(p)
    return serialize(p)

@router.delete("/projects/{project_id}")
def delete_project(project_id: uuid.UUID, reason: str, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    p = db.get(Project, project_id)
    if not p: raise HTTPException(404, "Projekt nicht gefunden")
    p.deleted_at = utcnow(); p.deleted_by = actor.user.id; p.delete_reason = reason; bump_version(p)
    db.commit(); return {"ok": True}

@router.get("/projects/{project_id}/members")
def list_members(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    return [{"id": str(x.id), "user_id": str(x.user_id), "role": x.role} for x in db.scalars(select(ProjectMembership).where(ProjectMembership.project_id == project_id))]

@router.post("/projects/{project_id}/members")
def add_member(project_id: uuid.UUID, payload: MemberCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    if payload.role not in {"project_lead", "project_member", "customer"}: raise HTTPException(422, "Ungültige Projektrolle")
    x = ProjectMembership(project_id=project_id, user_id=payload.user_id, role=payload.role, created_by=actor.user.id)
    db.add(x); db.commit()
    return {"id": str(x.id), "user_id": str(x.user_id), "role": x.role}

@router.post("/projects/{project_id}/restore")
def restore_project(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    p=db.get(Project,project_id)
    if not p:raise HTTPException(404,"Projekt nicht gefunden")
    require_tenant_access(db,actor,p.tenant_id,{"company_admin"})
    p.deleted_at=None;p.deleted_by=None;p.delete_reason=None;bump_version(p);db.commit();db.refresh(p);return serialize(p)
