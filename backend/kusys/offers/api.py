from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.artifacts.storage import persist_bytes
from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.common.config import get_settings
from kusys.common.security import utcnow
from kusys.offers.export import export_offer_docx, export_offer_xlsx
from kusys.offers.service import canonical, clone_version, freeze, persist_calculation, preview
from kusys.persistence.database import get_db
from kusys.persistence.models import (
    FileArtifact, Offer, OfferScopeItem, OfferSnapshot, OfferVersion, Project, PublishedArtifact, Requirement,
)

router=APIRouter(tags=["offers"])
settings=get_settings()

class OfferCreate(BaseModel):
    offer_number: str
    variant_name: str = "Basis"
    primary_variant: bool = True
    language: str = "de"

class OfferVersionUpdate(BaseModel):
    expected_version: int
    validity_days: int | None = None
    language: str | None = None
    risk_percent: Decimal | None = None
    discount_percent: Decimal | None = None
    vat_percent: Decimal | None = None
    template_version_id: uuid.UUID | None = None
    recipient: str | None = None
    customer_reference: str | None = None
    internal_reference: str | None = None
    payment_plan: list[dict] | None = None

class ScopeUpdate(BaseModel):
    included_requirement_ids: list[uuid.UUID]

class StatusRequest(BaseModel):
    target_status: str
    comment: str | None = None


def sv(v:OfferVersion)->dict:
    return {"id":str(v.id),"offer_id":str(v.offer_id),"version":v.version,"status":v.status,"offer_date":v.offer_date,"validity_days":v.validity_days,"language":v.language,"currency":v.currency,"risk_percent":str(v.risk_percent),"discount_percent":str(v.discount_percent),"vat_percent":str(v.vat_percent),"net_eur":str(v.net_eur),"gross_eur":str(v.gross_eur),"margin_eur":str(v.margin_eur),"baseline_id":str(v.baseline_id) if v.baseline_id else None,"recipient":v.recipient,"customer_reference":v.customer_reference,"internal_reference":v.internal_reference,"payment_plan":v.payment_plan,"lock_version":v.lock_version}

@router.get("/projects/{project_id}/offers")
def list_offers(project_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id)
    out=[]
    for o in db.scalars(select(Offer).where(Offer.project_id==project_id,Offer.deleted_at.is_(None)).order_by(Offer.offer_number,Offer.variant_name)):
        versions=list(db.scalars(select(OfferVersion).where(OfferVersion.offer_id==o.id).order_by(OfferVersion.version.desc())))
        out.append({"id":str(o.id),"offer_number":o.offer_number,"variant_name":o.variant_name,"primary_variant":o.primary_variant,"versions":[sv(v) for v in versions]})
    return out

@router.post("/projects/{project_id}/offers")
def create_offer(project_id:uuid.UUID,payload:OfferCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"});p=db.get(Project,project_id)
    if payload.primary_variant:
        for old in db.scalars(select(Offer).where(Offer.project_id==project_id,Offer.primary_variant.is_(True))):old.primary_variant=False
    o=Offer(tenant_id=p.tenant_id,project_id=project_id,offer_number=payload.offer_number,variant_name=payload.variant_name,primary_variant=payload.primary_variant,created_by=actor.user.id);db.add(o);db.flush()
    v=OfferVersion(offer_id=o.id,version=1,status="Entwurf",language=payload.language,vat_percent=Decimal(str(settings.vat_percent_default)),created_by=actor.user.id);db.add(v);db.flush()
    for r in db.scalars(select(Requirement).where(Requirement.project_id==project_id,Requirement.deleted_at.is_(None))):db.add(OfferScopeItem(offer_version_id=v.id,requirement_id=r.id,included=True,created_by=actor.user.id))
    db.commit();return {"offer_id":str(o.id),"version":sv(v)}

@router.post("/offers/{offer_id}/versions")
def new_version(offer_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    o=db.get(Offer,offer_id)
    if not o:raise HTTPException(404,"Angebot nicht gefunden")
    require_project_access(db,actor,o.project_id,{"project_lead","company_admin"})
    source=db.scalar(select(OfferVersion).where(OfferVersion.offer_id==offer_id).order_by(OfferVersion.version.desc()))
    v=clone_version(db,source,actor.user.id);db.commit();return sv(v)

@router.patch("/offer-versions/{version_id}")
def update_version(version_id:uuid.UUID,payload:OfferVersionUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id,{"project_lead","company_admin"})
    if v.status not in {"Entwurf","zur Freigabe"}:raise HTTPException(409,"Freigegebene Angebotsversionen sind unveränderlich")
    check_expected_version(v,payload.expected_version)
    data=payload.model_dump(exclude={"expected_version"},exclude_unset=True)
    if "payment_plan" in data and data["payment_plan"] is not None:
        total=sum(Decimal(str(x.get("percent",0))) for x in data["payment_plan"])
        if total != Decimal("100"): raise HTTPException(422,"Zahlungsplan muss exakt 100 % ergeben")
    for k,val in data.items():setattr(v,k,val)
    bump_version(v);data=preview(db,v);persist_calculation(db,v,data);db.commit();return sv(v)

@router.put("/offer-versions/{version_id}/scope")
def set_scope(version_id:uuid.UUID,payload:ScopeUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id,{"project_lead","company_admin"})
    if v.status not in {"Entwurf","zur Freigabe"}:raise HTTPException(409,"Freigegebene Angebotsversionen sind unveränderlich")
    allowed=set(db.scalars(select(Requirement.id).where(Requirement.project_id==o.project_id,Requirement.deleted_at.is_(None))))
    wanted=set(payload.included_requirement_ids)
    if not wanted.issubset(allowed):raise HTTPException(422,"Scope enthält unbekannte Anforderungen")
    existing={x.requirement_id:x for x in db.scalars(select(OfferScopeItem).where(OfferScopeItem.offer_version_id==v.id))}
    for rid in allowed:
        if rid in existing:existing[rid].included=rid in wanted
        else:db.add(OfferScopeItem(offer_version_id=v.id,requirement_id=rid,included=rid in wanted,created_by=actor.user.id))
    bump_version(v);data=preview(db,v);persist_calculation(db,v,data);db.commit();return data

@router.get("/offer-versions/{version_id}/preview")
def offer_preview(version_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id)
    snap=db.scalar(select(OfferSnapshot).where(OfferSnapshot.offer_version_id==v.id))
    return snap.snapshot_json if snap and v.status not in {"Entwurf","zur Freigabe"} else preview(db,v)

@router.post("/offer-versions/{version_id}/status")
def change_status(version_id:uuid.UUID,payload:StatusRequest,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id,{"project_lead","company_admin"})
    allowed={"Entwurf":{"zur Freigabe"},"zur Freigabe":{"Entwurf","freigegeben"},"freigegeben":{"versendet"},"versendet":{"angenommen","abgelehnt"},"angenommen":set(),"abgelehnt":set()}
    if payload.target_status not in allowed.get(v.status,set()):raise HTTPException(409,f"Statuswechsel {v.status} → {payload.target_status} ist nicht zulässig")
    if v.status=="zur Freigabe" and payload.target_status=="Entwurf" and not (payload.comment or "").strip():raise HTTPException(422,"Pflichtkommentar erforderlich")
    if payload.target_status=="freigegeben":
        if settings.four_eyes_default and v.created_by==actor.user.id:raise HTTPException(409,"Vier-Augen-Prinzip: Ersteller darf eigene Angebotsversion nicht freigeben")
        snap=freeze(db,v,actor.user.id)
        with NamedTemporaryFile(suffix=".docx",delete=False) as tmp: frozen_path=Path(tmp.name)
        try:
            export_offer_docx(frozen_path,snap.snapshot_json)
            artifact=persist_bytes(db,frozen_path.read_bytes(),tenant_id=o.tenant_id,project_id=o.project_id,filename=f"{o.offer_number}_{o.variant_name}_V{v.version}.docx",mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            db.add(PublishedArtifact(tenant_id=o.tenant_id,project_id=o.project_id,offer_version_id=v.id,file_artifact_id=artifact.id,kind="docx",language=v.language,immutable=True,created_by=actor.user.id))
            frozen=dict(snap.snapshot_json);frozen["frozen_docx"]={"artifact_id":str(artifact.id),"sha256":artifact.sha256,"filename":artifact.filename};snap.snapshot_json=frozen;snap.checksum=hashlib.sha256(canonical(frozen)).hexdigest()
        finally:
            frozen_path.unlink(missing_ok=True)
        v.approved_at=utcnow();v.approved_by=actor.user.id
    if payload.target_status=="versendet":
        if not db.scalar(select(OfferSnapshot).where(OfferSnapshot.offer_version_id==v.id)):raise HTTPException(409,"Versand erfordert freigegebenen Snapshot")
        v.sent_at=utcnow()
    v.status=payload.target_status;bump_version(v);db.commit();return sv(v)

@router.post("/offer-versions/{version_id}/export")
def export(version_id:uuid.UUID,format:str="docx",internal:bool=True,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id)
    snap=db.scalar(select(OfferSnapshot).where(OfferSnapshot.offer_version_id==v.id))
    fmt=format.lower()
    if fmt not in {"docx","xlsx"}:raise HTTPException(422,"Exportformat muss docx oder xlsx sein")
    if snap and v.status not in {"Entwurf","zur Freigabe"}:
        existing=db.scalar(select(PublishedArtifact).where(PublishedArtifact.offer_version_id==v.id,PublishedArtifact.kind==fmt,PublishedArtifact.immutable.is_(True)).order_by(PublishedArtifact.created_at.desc()))
        if existing:
            artifact=db.get(FileArtifact,existing.file_artifact_id)
            if artifact:return {"artifact_id":str(artifact.id),"filename":artifact.filename,"sha256":artifact.sha256}
    data=snap.snapshot_json if snap else preview(db,v)
    suffix=".docx" if fmt=="docx" else ".xlsx"
    with NamedTemporaryFile(suffix=suffix,delete=False) as tmp:path=Path(tmp.name)
    try:
        if suffix==".docx":export_offer_docx(path,data);mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:export_offer_xlsx(path,data,internal=internal);mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        bytes_=path.read_bytes();artifact=persist_bytes(db,bytes_,tenant_id=o.tenant_id,project_id=o.project_id,filename=f"{o.offer_number}_{o.variant_name}_V{v.version}{suffix}",mime_type=mime)
        db.add(PublishedArtifact(tenant_id=o.tenant_id,project_id=o.project_id,offer_version_id=v.id,file_artifact_id=artifact.id,kind=fmt,language=v.language,immutable=v.status not in {"Entwurf","zur Freigabe"},created_by=actor.user.id));db.commit()
        return {"artifact_id":str(artifact.id),"filename":artifact.filename,"sha256":artifact.sha256}
    finally:path.unlink(missing_ok=True)

class PositionCreate(BaseModel):
    position_no: str
    title: str
    description: str | None = None
    sales_eur: Decimal = Decimal("0")
    customer_visible_hours: bool = False

class TextBlockCreate(BaseModel):
    key: str
    content_html: str
    language: str = "de"

class TextBlockUpdate(BaseModel):
    expected_version: int
    content_html: str | None = None
    language: str | None = None


def _editable_offer_version(db: Session, actor: Actor, version_id: uuid.UUID) -> tuple[OfferVersion, Offer]:
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id,{"project_lead","company_admin"})
    if v.status not in {"Entwurf","zur Freigabe"}:raise HTTPException(409,"Freigegebene Angebotsversionen sind unveränderlich")
    return v,o

@router.get("/offer-versions/{version_id}/positions")
def positions(version_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id)
    from kusys.persistence.models import OfferPosition
    return [{"id":str(x.id),"position_no":x.position_no,"title":x.title,"description":x.description,"sales_eur":str(x.sales_eur),"customer_visible_hours":x.customer_visible_hours} for x in db.scalars(select(OfferPosition).where(OfferPosition.offer_version_id==version_id).order_by(OfferPosition.position_no))]

@router.post("/offer-versions/{version_id}/positions")
def add_position(version_id:uuid.UUID,payload:PositionCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    v,o=_editable_offer_version(db,actor,version_id)
    if payload.sales_eur<0:raise HTTPException(422,"Positionspreis darf nicht negativ sein")
    from kusys.persistence.models import OfferPosition
    x=OfferPosition(offer_version_id=v.id,created_by=actor.user.id,**payload.model_dump());db.add(x);bump_version(v);db.commit();db.refresh(x)
    return {"id":str(x.id),"position_no":x.position_no,"title":x.title,"description":x.description,"sales_eur":str(x.sales_eur),"customer_visible_hours":x.customer_visible_hours}

@router.delete("/offer-positions/{position_id}")
def delete_position(position_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    from kusys.persistence.models import OfferPosition
    x=db.get(OfferPosition,position_id)
    if not x:raise HTTPException(404,"Angebotsposition nicht gefunden")
    v,o=_editable_offer_version(db,actor,x.offer_version_id);db.delete(x);bump_version(v);db.commit();return {"status":"deleted"}

@router.get("/offer-versions/{version_id}/text-blocks")
def text_blocks(version_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    v=db.get(OfferVersion,version_id)
    if not v:raise HTTPException(404,"Angebotsversion nicht gefunden")
    o=db.get(Offer,v.offer_id);require_project_access(db,actor,o.project_id)
    from kusys.persistence.models import OfferTextBlock
    return [{"id":str(x.id),"key":x.key,"content_html":x.content_html,"language":x.language,"lock_version":x.lock_version} for x in db.scalars(select(OfferTextBlock).where(OfferTextBlock.offer_version_id==version_id).order_by(OfferTextBlock.key))]

@router.post("/offer-versions/{version_id}/text-blocks")
def add_text_block(version_id:uuid.UUID,payload:TextBlockCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    v,o=_editable_offer_version(db,actor,version_id)
    from kusys.persistence.models import OfferTextBlock
    existing=db.scalar(select(OfferTextBlock).where(OfferTextBlock.offer_version_id==version_id,OfferTextBlock.key==payload.key,OfferTextBlock.language==payload.language))
    if existing:raise HTTPException(409,"Textbaustein existiert bereits")
    x=OfferTextBlock(offer_version_id=v.id,created_by=actor.user.id,**payload.model_dump());db.add(x);bump_version(v);db.commit();db.refresh(x)
    return {"id":str(x.id),"key":x.key,"content_html":x.content_html,"language":x.language,"lock_version":x.lock_version}

@router.patch("/offer-text-blocks/{block_id}")
def update_text_block(block_id:uuid.UUID,payload:TextBlockUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    from kusys.persistence.models import OfferTextBlock
    x=db.get(OfferTextBlock,block_id)
    if not x:raise HTTPException(404,"Textbaustein nicht gefunden")
    v,o=_editable_offer_version(db,actor,x.offer_version_id);check_expected_version(x,payload.expected_version)
    for k,val in payload.model_dump(exclude={"expected_version"},exclude_unset=True).items():setattr(x,k,val)
    bump_version(x);bump_version(v);db.commit();return {"id":str(x.id),"key":x.key,"content_html":x.content_html,"language":x.language,"lock_version":x.lock_version}
