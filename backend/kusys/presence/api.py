from __future__ import annotations

import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.security import utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import PresenceSession, ProjectMembership, User

router=APIRouter(tags=["presence"])

class Heartbeat(BaseModel):
    area:str="overview"

@router.post("/projects/{project_id}/presence")
def heartbeat(project_id:uuid.UUID,payload:Heartbeat,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","project_member","company_admin","customer"})
    x=db.scalar(select(PresenceSession).where(PresenceSession.project_id==project_id,PresenceSession.user_id==actor.user.id))
    if not x:
        # tenant id resolved from project only after authorization
        from kusys.persistence.models import Project
        p=db.get(Project,project_id);x=PresenceSession(tenant_id=p.tenant_id,project_id=project_id,user_id=actor.user.id,area=payload.area)
        db.add(x)
    else:x.area=payload.area;x.last_heartbeat_at=utcnow()
    db.commit();return {"ok":True}

@router.get("/projects/{project_id}/presence")
def list_presence(project_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id)
    cutoff=utcnow()-timedelta(seconds=90);out=[]
    for x in db.scalars(select(PresenceSession).where(PresenceSession.project_id==project_id,PresenceSession.last_heartbeat_at>=cutoff)):
        u=db.get(User,x.user_id);pm=db.scalar(select(ProjectMembership).where(ProjectMembership.project_id==project_id,ProjectMembership.user_id==x.user_id))
        out.append({"user_id":str(x.user_id),"name":u.display_name if u else "?","project_role":pm.role if pm else "company_admin","area":x.area,"active":True,"last_heartbeat_at":x.last_heartbeat_at})
    return out
