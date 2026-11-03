from __future__ import annotations

import hashlib
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.persistence.database import get_db
from kusys.persistence.models import Baseline, BaselineRequirement, Project, Requirement

router = APIRouter(tags=["baselines"])

class BaselineCreate(BaseModel):
    name: str


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")

@router.get("/projects/{project_id}/baselines")
def list_baselines(project_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id)
    return [{"id":str(x.id),"name":x.name,"checksum":x.checksum,"created_at":x.created_at} for x in db.scalars(select(Baseline).where(Baseline.project_id==project_id).order_by(Baseline.created_at.desc()))]

@router.post("/projects/{project_id}/baselines")
def create_baseline(project_id:uuid.UUID,payload:BaselineCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"});p=db.get(Project,project_id)
    reqs=list(db.scalars(select(Requirement).where(Requirement.project_id==project_id,Requirement.deleted_at.is_(None)).order_by(Requirement.key)))
    items=[]
    for r in reqs:
        item={"id":str(r.id),"key":r.key,"title":r.title,"text":r.text,"priority":r.priority,"revision":r.business_revision,"source_refs":r.source_refs,"origin":r.origin,"budget_eur":str(r.budget_eur) if r.budget_eur is not None else None}
        items.append(item)
    snapshot={"project_id":str(project_id),"requirements":items}
    checksum=hashlib.sha256(canonical(snapshot)).hexdigest()
    b=Baseline(tenant_id=p.tenant_id,project_id=project_id,name=payload.name,checksum=checksum,snapshot_json=snapshot,created_by=actor.user.id);db.add(b);db.flush()
    for r,item in zip(reqs,items,strict=True):db.add(BaselineRequirement(baseline_id=b.id,requirement_id=r.id,requirement_revision=r.business_revision,snapshot_json=item,created_by=actor.user.id))
    db.commit();return {"id":str(b.id),"name":b.name,"checksum":b.checksum,"requirements":len(items)}
