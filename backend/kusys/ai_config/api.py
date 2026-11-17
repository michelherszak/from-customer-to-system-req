from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_tenant_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.config import get_settings
from kusys.common.security import encrypt_secret
from kusys.persistence.database import get_db
from kusys.persistence.models import AIModelPrice, AIProviderConfig, Tenant

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


class ModelSelection(BaseModel):
    tenant_id: uuid.UUID
    catalog_id: str
    api_key: SecretStr | None = None
    expected_version: int | None = None


@router.get("/ai-model-catalog")
def model_catalog(actor: Actor = Depends(require_actor)):
    from kusys.ai_config.catalog import CATALOG
    return [{k: v for k, v in x.items() if k != "endpoint"} for x in CATALOG]


@router.post("/ai-model-selection")
def select_cloud_model(payload: ModelSelection, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    from kusys.ai_config.catalog import selected_model
    require_tenant_access(db, actor, payload.tenant_id, {"company_admin"})
    model = selected_model(payload.catalog_id)
    if not model:
        raise HTTPException(422, "Modell ist nicht im Cloud-Katalog")
    key = payload.api_key.get_secret_value().strip() if payload.api_key else ""
    cfg = db.scalar(select(AIProviderConfig).where(AIProviderConfig.tenant_id == payload.tenant_id, AIProviderConfig.provider == model["provider"]))
    if cfg:
        if payload.expected_version is None:
            raise HTTPException(409, "Konfiguration wurde inzwischen angelegt; bitte neu laden")
        check_expected_version(cfg, payload.expected_version)
        if not key and not cfg.encrypted_api_key:
            raise HTTPException(422, "Bitte API-Schlüssel eingeben")
        cfg.endpoint = model["endpoint"]
        cfg.allowed_models = list(dict.fromkeys([*(cfg.allowed_models or []), model["model"]]))
        if key: cfg.encrypted_api_key = encrypt_secret(key, get_settings().master_key)
        bump_version(cfg)
    else:
        if not key: raise HTTPException(422, "Bitte API-Schlüssel eingeben")
        cfg = AIProviderConfig(tenant_id=payload.tenant_id, provider=model["provider"], endpoint=model["endpoint"],
            allowed_models=[model["model"]], confidential_allowed=False,
            encrypted_api_key=encrypt_secret(key, get_settings().master_key), created_by=actor.user.id)
        db.add(cfg)
    db.commit(); db.refresh(cfg)
    return {**serialize_provider(cfg), "selected_model": model["model"], "engine": "crewai"}


class AgentSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int
    default_provider_config_id: uuid.UUID | None = None
    default_model_id: str | None = Field(default=None, max_length=160)
    max_rounds: int = Field(default=2, ge=1, le=3)
    instructions: dict[str, str] = Field(default_factory=dict)


def agent_settings_response(tenant):
    from kusys.analysis.prompts import PROMPTS
    labels = {"document_preparer":"Dokumentaufbereitung", "requirements_engineer":"Requirements Engineer", "systems_engineer":"Systems Engineer", "work_planner":"Arbeitsplaner & Aufwandsschätzer", "review_engineer":"Review Engineer"}
    return {"tenant_id":str(tenant.id), "lock_version":tenant.lock_version,
        "settings":{"max_rounds":2,"instructions":{},**(tenant.agent_settings or {})},
        "agents":[{"id":role,"label":label,"default_prompt":PROMPTS[role]} for role,label in labels.items()]}


@router.get("/tenants/{tenant_id}/agent-settings")
def agent_settings(tenant_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_tenant_access(db,actor,tenant_id,{"company_admin"})
    tenant=db.get(Tenant,tenant_id)
    return agent_settings_response(tenant)


@router.put("/tenants/{tenant_id}/agent-settings")
def save_agent_settings(tenant_id: uuid.UUID, payload: AgentSettingsUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    from kusys.analysis.prompts import PROMPTS
    require_tenant_access(db,actor,tenant_id,{"company_admin"})
    tenant=db.scalar(select(Tenant).where(Tenant.id==tenant_id).with_for_update())
    check_expected_version(tenant,payload.expected_version)
    if set(payload.instructions)-set(PROMPTS) or any(len(text)>6000 for text in payload.instructions.values()):
        raise HTTPException(422,"Unbekannter Agent oder Zusatzanweisung länger als 6000 Zeichen")
    if bool(payload.default_provider_config_id) != bool(payload.default_model_id):
        raise HTTPException(422,"Standardanbieter und Modell gemeinsam auswählen")
    if payload.default_provider_config_id:
        cfg=db.get(AIProviderConfig,payload.default_provider_config_id)
        if not cfg or cfg.tenant_id!=tenant_id or not cfg.encrypted_api_key or payload.default_model_id not in (cfg.allowed_models or []):
            raise HTTPException(422,"Standardmodell ist für diese Firma nicht konfiguriert")
    tenant.agent_settings=payload.model_dump(mode="json",exclude={"expected_version"})
    bump_version(tenant);db.commit();db.refresh(tenant)
    return agent_settings_response(tenant)
