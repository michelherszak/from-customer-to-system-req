from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_tenant_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.persistence.database import get_db
from kusys.persistence.models import Customer

router = APIRouter(tags=["customers"])

class CustomerCreate(BaseModel):
    tenant_id: uuid.UUID
    customer_number: str
    company_name: str
    address: str | None = None
    country: str = "DE"
    contact_name: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None

class CustomerUpdate(BaseModel):
    expected_version: int
    company_name: str | None = None
    address: str | None = None
    contact_name: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None


def serialize(x: Customer) -> dict:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in {
        "id": x.id, "tenant_id": x.tenant_id, "customer_number": x.customer_number, "company_name": x.company_name,
        "address": x.address, "country": x.country, "contact_name": x.contact_name, "department": x.department,
        "email": x.email, "phone": x.phone, "lock_version": x.lock_version,
    }.items()}

@router.get("/customers")
def list_customers(tenant_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_tenant_access(db, actor, tenant_id)
    return [serialize(x) for x in db.scalars(select(Customer).where(Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None)).order_by(Customer.company_name))]

@router.post("/customers")
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_tenant_access(db, actor, payload.tenant_id, {"company_admin"})
    x = Customer(**payload.model_dump(), created_by=actor.user.id)
    db.add(x); db.commit(); db.refresh(x)
    return serialize(x)

@router.patch("/customers/{customer_id}")
def update_customer(customer_id: uuid.UUID, payload: CustomerUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    x = db.get(Customer, customer_id)
    if not x: raise HTTPException(404, "Kunde nicht gefunden")
    require_tenant_access(db, actor, x.tenant_id, {"company_admin"})
    check_expected_version(x, payload.expected_version)
    for k, v in payload.model_dump(exclude={"expected_version"}, exclude_none=True).items(): setattr(x, k, v)
    bump_version(x); db.commit(); db.refresh(x)
    return serialize(x)
