from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, create_user, require_actor, require_csrf, require_tenant_access
from kusys.persistence.database import get_db
from kusys.persistence.models import TenantMembership, User

router=APIRouter(tags=["users"])

class UserCreate(BaseModel):
    tenant_id:uuid.UUID
    username:str
    display_name:str
    password:str
    email:str|None=None
    role:str="project_member"

@router.get("/users")
def users(tenant_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_tenant_access(db,actor,tenant_id,{"company_admin"})
    rows=db.execute(select(User,TenantMembership.role).join(TenantMembership,TenantMembership.user_id==User.id).where(TenantMembership.tenant_id==tenant_id,User.deleted_at.is_(None))).all()
    return [{"id":str(u.id),"username":u.username,"display_name":u.display_name,"email":u.email,"role":role,"active":u.active} for u,role in rows]

@router.post("/users")
def create(payload:UserCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_tenant_access(db,actor,payload.tenant_id,{"company_admin"})
    if payload.role not in {"company_admin","project_lead","project_member","customer"}:raise HTTPException(422,"Ungültige Rolle")
    try:u=create_user(db,payload.username,payload.display_name,payload.password,payload.email)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    db.add(TenantMembership(tenant_id=payload.tenant_id,user_id=u.id,role=payload.role,created_by=actor.user.id));db.commit()
    return {"id":str(u.id),"username":u.username,"role":payload.role}
