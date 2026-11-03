from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.security import utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import MaterialItem, Project, Requirement

router = APIRouter(tags=["commercial"])

class MaterialCreate(BaseModel):
    description: str
    cost_eur: Decimal = Decimal("0")
    sales_eur: Decimal = Decimal("0")
    requirement_ids: list[uuid.UUID] = Field(default_factory=list)
    scaling_mode: str = "proportional"

class MaterialUpdate(BaseModel):
    expected_version: int
    description: str | None = None
    cost_eur: Decimal | None = None
    sales_eur: Decimal | None = None
    requirement_ids: list[uuid.UUID] | None = None
    scaling_mode: str | None = None


def serialize(x: MaterialItem) -> dict:
    return {
        "id": str(x.id), "key": x.key, "description": x.description,
        "cost_eur": str(x.cost_eur), "sales_eur": str(x.sales_eur),
        "requirement_ids": [str(v) for v in (x.requirement_ids or [])],
        "scaling_mode": x.scaling_mode, "lock_version": x.lock_version,
        "deleted": x.deleted_at is not None,
    }


def _validate_requirements(db: Session, project_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    if not ids:
        return
    count = db.scalar(select(func.count(Requirement.id)).where(
        Requirement.project_id == project_id,
        Requirement.id.in_(ids),
        Requirement.deleted_at.is_(None),
    )) or 0
    if count != len(set(ids)):
        raise HTTPException(422, "Mindestens eine Anforderung gehört nicht zum Projekt")


@router.get("/projects/{project_id}/materials")
def list_materials(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    rows = db.scalars(select(MaterialItem).where(MaterialItem.project_id == project_id, MaterialItem.deleted_at.is_(None)).order_by(MaterialItem.key))
    return [serialize(x) for x in rows]


@router.post("/projects/{project_id}/materials")
def create_material(project_id: uuid.UUID, payload: MaterialCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "project_member", "company_admin"})
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Projekt nicht gefunden")
    if payload.cost_eur < 0 or payload.sales_eur < 0:
        raise HTTPException(422, "Kosten und Verkaufspreis dürfen nicht negativ sein")
    if payload.scaling_mode not in {"proportional", "full_if_used"}:
        raise HTTPException(422, "Unbekannte Skalierungsart")
    _validate_requirements(db, project_id, payload.requirement_ids)
    max_no = 0
    for key in db.scalars(select(MaterialItem.key).where(MaterialItem.project_id == project_id)):
        try:
            max_no = max(max_no, int(key.split("-")[-1]))
        except ValueError:
            pass
    item = MaterialItem(
        tenant_id=p.tenant_id, project_id=project_id, key=f"MAT-{max_no + 1:03d}",
        description=payload.description, cost_eur=payload.cost_eur, sales_eur=payload.sales_eur,
        requirement_ids=[str(x) for x in payload.requirement_ids], scaling_mode=payload.scaling_mode,
        created_by=actor.user.id,
    )
    db.add(item); db.commit(); db.refresh(item)
    return serialize(item)


@router.patch("/materials/{material_id}")
def update_material(material_id: uuid.UUID, payload: MaterialUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    item = db.get(MaterialItem, material_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(404, "Sachposition nicht gefunden")
    require_project_access(db, actor, item.project_id, {"project_lead", "project_member", "company_admin"})
    check_expected_version(item, payload.expected_version)
    data = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "cost_eur" in data and data["cost_eur"] < 0 or "sales_eur" in data and data["sales_eur"] < 0:
        raise HTTPException(422, "Kosten und Verkaufspreis dürfen nicht negativ sein")
    if data.get("scaling_mode") not in {None, "proportional", "full_if_used"}:
        raise HTTPException(422, "Unbekannte Skalierungsart")
    if "requirement_ids" in data:
        _validate_requirements(db, item.project_id, data["requirement_ids"] or [])
        data["requirement_ids"] = [str(x) for x in (data["requirement_ids"] or [])]
    for k, v in data.items():
        setattr(item, k, v)
    bump_version(item); db.commit(); db.refresh(item)
    return serialize(item)


@router.delete("/materials/{material_id}")
def delete_material(material_id: uuid.UUID, reason: str, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    item = db.get(MaterialItem, material_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(404, "Sachposition nicht gefunden")
    require_project_access(db, actor, item.project_id, {"project_lead", "project_member", "company_admin"})
    if not reason.strip():
        raise HTTPException(422, "Löschgrund ist erforderlich")
    item.deleted_at = utcnow(); item.deleted_by = actor.user.id; item.delete_reason = reason; bump_version(item)
    db.commit(); return {"status": "deleted", "id": str(item.id)}


@router.post("/materials/{material_id}/restore")
def restore_material(material_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    item = db.get(MaterialItem, material_id)
    if not item:
        raise HTTPException(404, "Sachposition nicht gefunden")
    require_project_access(db, actor, item.project_id, {"project_lead", "company_admin"})
    item.deleted_at = None; item.deleted_by = None; item.delete_reason = None; bump_version(item)
    db.commit(); return serialize(item)
