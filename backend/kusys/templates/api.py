from __future__ import annotations

import io
import uuid
import zipfile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.artifacts.storage import persist_bytes
from kusys.auth.service import Actor, require_actor, require_csrf, require_tenant_access
from kusys.persistence.database import get_db
from kusys.persistence.models import DocumentTemplate, DocumentTemplateVersion

router=APIRouter(tags=["templates"])


class TemplateCreate(BaseModel):
    tenant_id: uuid.UUID
    name: str
    config_json: dict = Field(default_factory=dict)
    content_blocks: list = Field(default_factory=list)


class TemplateVersionCreate(BaseModel):
    config_json: dict = Field(default_factory=dict)
    content_blocks: list = Field(default_factory=list)


class TemplateVersionUpdate(BaseModel):
    config_json: dict | None = None
    content_blocks: list | None = None


def _serialize_version(v: DocumentTemplateVersion) -> dict:
    return {"id":str(v.id),"version":v.version,"status":v.status,"config_json":v.config_json,"content_blocks":v.content_blocks,"master_artifact_id":str(v.master_artifact_id) if v.master_artifact_id else None}


def _validate_blocks(v: DocumentTemplateVersion) -> None:
    required=[b.get("placeholder") for b in v.content_blocks if isinstance(b,dict) and b.get("required")]
    known={"offer_number","project_name","customer_name","net","vat","gross","schedule_finish","schedule","price","positions","requirements","payment_plan"}
    unknown=[x for x in required if x and x not in known]
    if unknown: raise HTTPException(422,{"code":"unknown_required_placeholders","placeholders":unknown})
    missing_translation=[]
    for b in v.content_blocks:
        if not isinstance(b,dict) or not b.get("required_translations"): continue
        translations=b.get("translations") or {}
        for lang in b["required_translations"]:
            if not str(translations.get(lang,"")).strip(): missing_translation.append({"block":b.get("key") or b.get("placeholder"),"language":lang})
    if missing_translation: raise HTTPException(422,{"code":"missing_required_translations","items":missing_translation})


def _validate_docx_master(data: bytes) -> None:
    if len(data) > 50 * 1024 * 1024: raise HTTPException(413,"DOCX-Master ist zu groß")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names={n.lower() for n in z.namelist()}
            if any("vbaproject.bin" in n or n.endswith(".bin") for n in names):
                raise HTTPException(422,"Makros oder ausführbare Binärinhalte sind nicht zulässig")
            for name in z.namelist():
                if name.lower().endswith(".rels"):
                    text=z.read(name).decode("utf-8",errors="ignore")
                    if 'TargetMode="External"' in text or "TargetMode='External'" in text:
                        raise HTTPException(422,"Aktive externe Inhalte sind nicht zulässig")
            if "word/document.xml" not in names: raise HTTPException(422,"Ungültige DOCX-Datei")
    except zipfile.BadZipFile as exc:
        raise HTTPException(422,"Ungültige DOCX-Datei") from exc


@router.get("/templates")
def list_templates(tenant_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_tenant_access(db,actor,tenant_id)
    out=[]
    for t in db.scalars(select(DocumentTemplate).where(DocumentTemplate.tenant_id==tenant_id,DocumentTemplate.deleted_at.is_(None)).order_by(DocumentTemplate.name)):
        versions=list(db.scalars(select(DocumentTemplateVersion).where(DocumentTemplateVersion.template_id==t.id).order_by(DocumentTemplateVersion.version.desc())))
        out.append({"id":str(t.id),"name":t.name,"kind":t.kind,"versions":[_serialize_version(v) for v in versions]})
    return out


@router.post("/templates")
def create_template(payload:TemplateCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_tenant_access(db,actor,payload.tenant_id,{"company_admin"})
    t=DocumentTemplate(tenant_id=payload.tenant_id,name=payload.name,created_by=actor.user.id);db.add(t);db.flush()
    v=DocumentTemplateVersion(template_id=t.id,version=1,status="Entwurf",config_json=payload.config_json,content_blocks=payload.content_blocks,created_by=actor.user.id);db.add(v);db.commit()
    return {"id":str(t.id),"version":_serialize_version(v)}


@router.post("/templates/{template_id}/versions")
def new_version(template_id:uuid.UUID,payload:TemplateVersionCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    t=db.get(DocumentTemplate,template_id)
    if not t:raise HTTPException(404,"Vorlage nicht gefunden")
    require_tenant_access(db,actor,t.tenant_id,{"company_admin"})
    n=(db.scalar(select(func.max(DocumentTemplateVersion.version)).where(DocumentTemplateVersion.template_id==template_id)) or 0)+1
    v=DocumentTemplateVersion(template_id=t.id,version=n,status="Entwurf",config_json=payload.config_json,content_blocks=payload.content_blocks,created_by=actor.user.id);db.add(v);db.commit();return _serialize_version(v)


@router.patch("/templates/{template_id}/versions/{version_id}")
def update_version(template_id:uuid.UUID,version_id:uuid.UUID,payload:TemplateVersionUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    t=db.get(DocumentTemplate,template_id);v=db.get(DocumentTemplateVersion,version_id)
    if not t or not v or v.template_id!=template_id:raise HTTPException(404,"Vorlagenversion nicht gefunden")
    require_tenant_access(db,actor,t.tenant_id,{"company_admin"})
    if v.status!="Entwurf":raise HTTPException(409,"Veröffentlichte oder archivierte Vorlagenversionen sind unveränderlich")
    if payload.config_json is not None:v.config_json=payload.config_json
    if payload.content_blocks is not None:v.content_blocks=payload.content_blocks
    db.commit();return _serialize_version(v)


@router.post("/templates/{template_id}/versions/{version_id}/master-docx")
def upload_master(template_id:uuid.UUID,version_id:uuid.UUID,file:UploadFile=File(...),db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    t=db.get(DocumentTemplate,template_id);v=db.get(DocumentTemplateVersion,version_id)
    if not t or not v or v.template_id!=template_id:raise HTTPException(404,"Vorlagenversion nicht gefunden")
    require_tenant_access(db,actor,t.tenant_id,{"company_admin"})
    if v.status!="Entwurf":raise HTTPException(409,"Nur Entwürfe dürfen geändert werden")
    if not (file.filename or "").lower().endswith(".docx"):raise HTTPException(422,"Nur DOCX-Master sind zulässig")
    data=file.file.read();_validate_docx_master(data)
    artifact=persist_bytes(db,data,tenant_id=t.tenant_id,project_id=None,filename=file.filename or "master.docx",mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    v.master_artifact_id=artifact.id;db.commit();return {"master_artifact_id":str(artifact.id),"sha256":artifact.sha256}


@router.post("/templates/{template_id}/versions/{version_id}/publish")
def publish(template_id:uuid.UUID,version_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    t=db.get(DocumentTemplate,template_id);v=db.get(DocumentTemplateVersion,version_id)
    if not t or not v or v.template_id!=template_id:raise HTTPException(404,"Vorlagenversion nicht gefunden")
    require_tenant_access(db,actor,t.tenant_id,{"company_admin"})
    if v.status!="Entwurf":raise HTTPException(409,"Nur Entwürfe können veröffentlicht werden")
    _validate_blocks(v);v.status="veröffentlicht";db.commit();return _serialize_version(v)


@router.post("/templates/{template_id}/versions/{version_id}/archive")
def archive(template_id:uuid.UUID,version_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    t=db.get(DocumentTemplate,template_id);v=db.get(DocumentTemplateVersion,version_id)
    if not t or not v or v.template_id!=template_id:raise HTTPException(404,"Vorlagenversion nicht gefunden")
    require_tenant_access(db,actor,t.tenant_id,{"company_admin"})
    if v.status=="Entwurf":raise HTTPException(409,"Entwürfe werden nicht archiviert; sie können als neue Version weiterbearbeitet werden")
    v.status="archiviert";db.commit();return _serialize_version(v)
