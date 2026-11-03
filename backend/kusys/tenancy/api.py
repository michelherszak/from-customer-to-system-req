from __future__ import annotations

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_tenant_access
from kusys.persistence.database import get_db
from kusys.persistence.models import PlatformAccessGrant, PlatformAccessRequest, Tenant, TenantMembership

router = APIRouter(tags=["tenancy"])

class AccessRequestIn(BaseModel):
    tenant_id: uuid.UUID
    reason: str
    requested_until: datetime

class AccessGrantIn(BaseModel):
    request_id: uuid.UUID

@router.get("/tenants")
def tenants(db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    rows = db.execute(select(Tenant, TenantMembership.role).join(TenantMembership, TenantMembership.tenant_id == Tenant.id).where(TenantMembership.user_id == actor.user.id)).all()
    return [{"id": str(t.id), "name": t.name, "role": role, "currency": t.currency, "timezone": t.timezone} for t, role in rows]

@router.post("/platform-access-requests")
def request_access(payload: AccessRequestIn, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    if not actor.user.is_platform_admin: raise HTTPException(403, "Nur Plattform-Admins können Zugriff anfragen")
    x = PlatformAccessRequest(tenant_id=payload.tenant_id, requester_id=actor.user.id, reason=payload.reason, requested_until=payload.requested_until, created_by=actor.user.id)
    db.add(x); db.commit(); return {"id": str(x.id), "status": x.status}

@router.post("/platform-access-grants")
def grant_access(payload: AccessGrantIn, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    req = db.get(PlatformAccessRequest, payload.request_id)
    if not req: raise HTTPException(404, "Anfrage nicht gefunden")
    require_tenant_access(db, actor, req.tenant_id, {"company_admin"})
    req.status = "approved"
    grant = PlatformAccessGrant(tenant_id=req.tenant_id, requester_id=req.requester_id, approver_id=actor.user.id, reason=req.reason, valid_until=req.requested_until, created_by=actor.user.id)
    db.add(grant); db.commit(); return {"id": str(grant.id), "status": grant.status, "valid_until": grant.valid_until}
