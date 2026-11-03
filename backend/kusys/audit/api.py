from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_project_access
from kusys.persistence.database import get_db
from kusys.persistence.models import AuditEvent

router=APIRouter(tags=["audit"])

@router.get("/projects/{project_id}/audit")
def audit_events(project_id:uuid.UUID,limit:int=200,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"})
    rows=db.scalars(select(AuditEvent).where(AuditEvent.project_id==project_id).order_by(AuditEvent.occurred_at.desc()).limit(min(limit,1000)))
    return [{"id":str(x.id),"action":x.action,"entity_type":x.entity_type,"entity_id":x.entity_id,"user_id":str(x.user_id) if x.user_id else None,"metadata":x.metadata_json,"occurred_at":x.occurred_at} for x in rows]
