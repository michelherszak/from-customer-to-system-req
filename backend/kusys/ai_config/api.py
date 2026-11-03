from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_tenant_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.config import get_settings
from kusys.common.security import encrypt_secret
from kusys.persistence.database import get_db
from kusys.persistence.models import AIModelPrice, AIProviderConfig

router = APIRouter(tags=["ai-config"])

class ProviderCreate(BaseModel):
    tenant_id: uuid.UUID
    provider: str
    endpoint: str | None = None
    region: str | None = None
    deployment: str | None = None
    allowed_models: list[str] = Field(default_factory=list)
    confidential_allowed: bool = False
    api_key: str | None = None

class ProviderUpdate(BaseModel):
    expected_version: int
    endpoint: str | None = None
    region: str | None = None
    deployment: str | None = None
    allowed_models: list[str] | None = None
    confidential_allowed: bool | None = None
    api_key: str | None = None

class PriceCreate(BaseModel):
    provider: str
    model_id: str
    currency: str = "EUR"
    input_per_million: Decimal = Decimal("0")
    output_per_million: Decimal = Decimal("0")


def serialize_provider(x: AIProviderConfig) -> dict:
    return {"id": str(x.id), "provider": x.provider, "endpoint": x.endpoint, "region": x.region, "deployment": x.deployment, "allowed_models": x.allowed_models, "confidential_allowed": x.confidential_allowed, "has_api_key": bool(x.encrypted_api_key), "lock_version": x.lock_version}


@router.get("/tenants/{tenant_id}/ai-providers")
def list_providers(tenant_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_tenant_access(db, actor, tenant_id, {"company_admin"})
    return [serialize_provider(x) for x in db.scalars(select(AIProviderConfig).where(AIProviderConfig.tenant_id == tenant_id).order_by(AIProviderConfig.provider))]


@router.post("/ai-providers")
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_tenant_access(db, actor, payload.tenant_id, {"company_admin"})
    if db.scalar(select(AIProviderConfig).where(AIProviderConfig.tenant_id == payload.tenant_id, AIProviderConfig.provider == payload.provider)):
        raise HTTPException(409, "Provider ist bereits konfiguriert")
    data = payload.model_dump(exclude={"api_key"})
    x = AIProviderConfig(created_by=actor.user.id, encrypted_api_key=encrypt_secret(payload.api_key, get_settings().master_key) if payload.api_key else None, **data); db.add(x); db.commit(); db.refresh(x)
    return serialize_provider(x)


@router.patch("/ai-providers/{provider_id}")
def update_provider(provider_id: uuid.UUID, payload: ProviderUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    x = db.get(AIProviderConfig, provider_id)
    if not x: raise HTTPException(404, "Provider nicht gefunden")
    require_tenant_access(db, actor, x.tenant_id, {"company_admin"}); check_expected_version(x, payload.expected_version)
    data = payload.model_dump(exclude={"expected_version", "api_key"}, exclude_unset=True)
    for k, v in data.items(): setattr(x, k, v)
    if payload.api_key is not None: x.encrypted_api_key = encrypt_secret(payload.api_key, get_settings().master_key) if payload.api_key else None
    bump_version(x); db.commit(); return serialize_provider(x)


@router.get("/ai-model-prices")
def model_prices(provider: str | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    q = select(AIModelPrice)
    if provider: q = q.where(AIModelPrice.provider == provider)
    return [{"id": str(x.id), "provider": x.provider, "model_id": x.model_id, "currency": x.currency, "input_per_million": str(x.input_per_million), "output_per_million": str(x.output_per_million), "valid_from": x.valid_from.isoformat() if x.valid_from else None} for x in db.scalars(q.order_by(AIModelPrice.provider, AIModelPrice.model_id))]


@router.post("/ai-model-prices")
def create_model_price(payload: PriceCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    # Model prices are installation-wide commercial metadata and may only be maintained
    # by a platform administrator. Tenant administrators can read them for transparency.
    if actor.role != "platform_admin":
        raise HTTPException(403, "Nur Plattform-Admins dürfen Modellpreise pflegen")
    x = AIModelPrice(
        provider=payload.provider.strip(), model_id=payload.model_id.strip(), currency=payload.currency.upper(),
        input_per_million=payload.input_per_million, output_per_million=payload.output_per_million,
        created_by=actor.user.id,
    )
    db.add(x); db.commit(); db.refresh(x)
    return {"id": str(x.id), "provider": x.provider, "model_id": x.model_id, "currency": x.currency,
            "input_per_million": str(x.input_per_million), "output_per_million": str(x.output_per_million),
            "valid_from": x.valid_from.isoformat() if x.valid_from else None}
