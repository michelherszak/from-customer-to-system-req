from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, login, logout, require_actor, require_csrf, serialize_user
from kusys.persistence.database import get_db
from kusys.persistence.models import ProjectMembership, TenantMembership

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login_route(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return login(db, request, response, payload.username, payload.password)


@router.post("/logout")
def logout_route(response: Response, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    logout(db, response, actor)
    return {"ok": True}


@router.get("/me")
def me(db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    tenant_roles = [
        {"tenant_id": str(x.tenant_id), "role": x.role}
        for x in db.scalars(select(TenantMembership).where(TenantMembership.user_id == actor.user.id))
    ]
    project_roles = [
        {"project_id": str(x.project_id), "role": x.role}
        for x in db.scalars(select(ProjectMembership).where(ProjectMembership.user_id == actor.user.id))
    ]
    return {
        "user": serialize_user(actor.user),
        "tenant_roles": tenant_roles,
        "project_roles": project_roles,
        "csrf_token": actor.session.csrf_token,
    }
