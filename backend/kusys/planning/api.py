from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.analysis.service import work_package_snapshot
from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access, require_tenant_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.persistence.database import get_db
from kusys.persistence.models import (
    Project, RateCard, RateCardRole, WorkPackage as WPModel, WorkPackageDependency, WorkPackageRequirement, WorkPackageRevision,
)
from kusys.planning.engine import PlanningEngine, PlanningError
from kusys.services.calculation import ensure_project_rate_card, ensure_tenant_rate_card, load_calculation_inputs

router = APIRouter(tags=["planning"])

class WorkPackageUpdate(BaseModel):
    expected_version: int
    name: str | None = None
    description: str | None = None
    role_name: str | None = None
    min_hours: int | None = None
    likely_hours: int | None = None
    max_hours: int | None = None
    plan_hours: int | None = None
    max_fte: Decimal | None = None
    planning_priority: int | None = None
    phase: str | None = None
    global_package: bool | None = None
    scaling_mode: str | None = None

class WorkPackageCreate(BaseModel):
    name: str
    description: str | None = None
    role_name: str = "Systems Engineering"
    min_hours: int = 8
    likely_hours: int = 16
    max_hours: int = 24
    plan_hours: int = 16
    max_fte: Decimal = Decimal("1")
    planning_priority: int = 3
    phase: str = "Realisierung"
    global_package: bool = False
    scaling_mode: str = "proportional"
    requirement_ids: list[uuid.UUID] = []

class DependencyCreate(BaseModel):
    predecessor_id: uuid.UUID

class RateUpdate(BaseModel):
    expected_version: int
    capacity_fte: Decimal | None = None
    internal_cost_rate: Decimal | None = None
    purchase_rate: Decimal | None = None
    markup_percent: Decimal | None = None
    sales_rate: Decimal | None = None


def validate_hours(min_h: int, likely: int, max_h: int) -> None:
    if not (0 <= min_h <= likely <= max_h): raise HTTPException(422, "Es muss 0 ≤ min ≤ wahrscheinlich ≤ max gelten")


def serialize_wp(wp: WPModel, links: list[WorkPackageRequirement] | None = None) -> dict:
    return {"id": str(wp.id), "key": wp.key, "name": wp.name, "description": wp.description, "role_name": wp.role_name, "min_hours": wp.min_hours, "likely_hours": wp.likely_hours, "max_hours": wp.max_hours, "plan_hours": wp.plan_hours, "max_fte": str(wp.max_fte), "planning_priority": wp.planning_priority, "phase": wp.phase, "global_package": wp.global_package, "scaling_mode": wp.scaling_mode, "lock_version": wp.lock_version, "requirement_ids": [str(x.requirement_id) for x in (links or [])]}

@router.get("/projects/{project_id}/work-packages")
def list_work_packages(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    out=[]
    for wp in db.scalars(select(WPModel).where(WPModel.project_id==project_id, WPModel.deleted_at.is_(None)).order_by(WPModel.key)):
        links=list(db.scalars(select(WorkPackageRequirement).where(WorkPackageRequirement.work_package_id==wp.id)))
        deps=list(db.scalars(select(WorkPackageDependency).where(WorkPackageDependency.successor_id==wp.id, WorkPackageDependency.active.is_(True))))
        out.append({**serialize_wp(wp,links), "predecessor_ids":[str(x.predecessor_id) for x in deps]})
    return out

@router.post("/projects/{project_id}/work-packages")
def create_work_package(project_id: uuid.UUID, payload: WorkPackageCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead","project_member","company_admin"})
    validate_hours(payload.min_hours,payload.likely_hours,payload.max_hours)
    p=db.get(Project,project_id); max_no=0
    for key in db.scalars(select(WPModel.key).where(WPModel.project_id==project_id)):
        try:max_no=max(max_no,int(key.split("-")[-1]))
        except:pass
    data=payload.model_dump(exclude={"requirement_ids"})
    wp=WPModel(tenant_id=p.tenant_id,project_id=project_id,key=f"AP-{max_no+1:03d}",created_by=actor.user.id,**data)
    db.add(wp);db.flush();db.add(WorkPackageRevision(work_package_id=wp.id,revision_no=1,snapshot=work_package_snapshot(wp),created_by=actor.user.id))
    for rid in payload.requirement_ids: db.add(WorkPackageRequirement(work_package_id=wp.id,requirement_id=rid,created_by=actor.user.id))
    db.commit();return serialize_wp(wp,list(db.scalars(select(WorkPackageRequirement).where(WorkPackageRequirement.work_package_id==wp.id))))

@router.patch("/work-packages/{wp_id}")
def update_work_package(wp_id: uuid.UUID,payload:WorkPackageUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    wp=db.get(WPModel,wp_id)
    if not wp or wp.deleted_at:raise HTTPException(404,"Arbeitspaket nicht gefunden")
    require_project_access(db,actor,wp.project_id,{"project_lead","project_member","company_admin"});check_expected_version(wp,payload.expected_version)
    data=payload.model_dump(exclude={"expected_version"},exclude_unset=True)
    test={"min_hours":data.get("min_hours",wp.min_hours),"likely_hours":data.get("likely_hours",wp.likely_hours),"max_hours":data.get("max_hours",wp.max_hours)}
    validate_hours(test["min_hours"],test["likely_hours"],test["max_hours"])
    if "planning_priority" in data and not 1<=data["planning_priority"]<=5:raise HTTPException(422,"Planungspriorität muss 1-5 sein")
    for k,v in data.items():setattr(wp,k,v)
    wp.business_revision+=1;bump_version(wp);db.add(WorkPackageRevision(work_package_id=wp.id,revision_no=wp.business_revision,snapshot=work_package_snapshot(wp),created_by=actor.user.id));db.commit();db.refresh(wp)
    return serialize_wp(wp,list(db.scalars(select(WorkPackageRequirement).where(WorkPackageRequirement.work_package_id==wp.id))))

@router.post("/work-packages/{wp_id}/dependencies")
def add_dependency(wp_id:uuid.UUID,payload:DependencyCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    wp=db.get(WPModel,wp_id);pred=db.get(WPModel,payload.predecessor_id)
    if not wp or not pred or wp.project_id!=pred.project_id:raise HTTPException(404,"Arbeitspaket nicht gefunden")
    require_project_access(db,actor,wp.project_id,{"project_lead","project_member","company_admin"})
    dep=WorkPackageDependency(predecessor_id=pred.id,successor_id=wp.id,created_by=actor.user.id);db.add(dep);db.flush()
    # Validate cycle by running schedule; rollback if invalid.
    try:
        _,_,wps,_,_,caps,_,_,start,holidays,hpd,weekdays=load_calculation_inputs(db,wp.project_id)
        PlanningEngine().schedule(wps,caps,start,holidays,hpd,weekdays)
    except PlanningError as exc:
        db.rollback();raise HTTPException(422,{"code":"dependency_cycle","message":str(exc)}) from exc
    db.commit();return {"id":str(dep.id),"predecessor_id":str(dep.predecessor_id),"successor_id":str(dep.successor_id)}

@router.get("/projects/{project_id}/schedule")
def schedule(project_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id)
    _,_,wps,_,_,caps,_,_,start,holidays,hpd,weekdays=load_calculation_inputs(db,project_id)
    try:r=PlanningEngine().schedule(wps,caps,start,holidays,hpd,weekdays)
    except PlanningError as exc:raise HTTPException(422,str(exc)) from exc
    return {"project_start":start,"project_finish":r.project_finish,"critical_path":list(r.critical_path),"packages":[{"id":x.id,"start":x.start,"finish":x.finish,"duration_days":x.duration_days,"total_float_days":x.total_float_days,"critical":x.critical} for x in r.packages]}

@router.get("/projects/{project_id}/rate-card")
def rate_card(project_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id);p=db.get(Project,project_id);card=ensure_project_rate_card(db,p,actor.user.id);db.commit()
    roles=list(db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id==card.id).order_by(RateCardRole.name)))
    return {"id":str(card.id),"name":card.name,"lock_version":card.lock_version,"roles":[{"id":str(x.id),"name":x.name,"kind":x.kind,"capacity_fte":str(x.capacity_fte),"internal_cost_rate":str(x.internal_cost_rate) if x.internal_cost_rate is not None else None,"purchase_rate":str(x.purchase_rate) if x.purchase_rate is not None else None,"markup_percent":str(x.markup_percent) if x.markup_percent is not None else None,"sales_rate":str(x.sales_rate),"lock_version":x.lock_version} for x in roles]}

@router.patch("/rate-card-roles/{role_id}")
def update_rate(role_id:uuid.UUID,payload:RateUpdate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    role=db.get(RateCardRole,role_id)
    if not role:raise HTTPException(404,"Rolle nicht gefunden")
    from kusys.persistence.models import RateCard
    card=db.get(RateCard,role.rate_card_id)
    if not card or not card.project_id:raise HTTPException(422,"Firmenvorlage kann hier nicht geändert werden")
    require_project_access(db,actor,card.project_id,{"project_lead","company_admin"});check_expected_version(role,payload.expected_version)
    for k,v in payload.model_dump(exclude={"expected_version"},exclude_unset=True).items():setattr(role,k,v)
    bump_version(role);db.commit();return {"id":str(role.id),"name":role.name,"lock_version":role.lock_version}

class RateRoleCreate(BaseModel):
    name: str
    aliases: list[str] = []
    kind: str = "internal"
    capacity_fte: Decimal = Decimal("1")
    internal_cost_rate: Decimal | None = None
    purchase_rate: Decimal | None = None
    markup_percent: Decimal | None = None
    sales_rate: Decimal = Decimal("0")

@router.post("/projects/{project_id}/rate-card/roles")
def create_rate_role(project_id:uuid.UUID,payload:RateRoleCreate,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"});p=db.get(Project,project_id);card=ensure_project_rate_card(db,p,actor.user.id)
    if payload.kind not in {"internal","external"}:raise HTTPException(422,"Art muss internal oder external sein")
    if payload.capacity_fte<0 or payload.sales_rate<0:raise HTTPException(422,"Kapazität und Sätze dürfen nicht negativ sein")
    if db.scalar(select(RateCardRole).where(RateCardRole.rate_card_id==card.id,RateCardRole.name==payload.name)):raise HTTPException(409,"Rolle existiert bereits")
    role=RateCardRole(rate_card_id=card.id,created_by=actor.user.id,**payload.model_dump());db.add(role);db.commit();db.refresh(role)
    return {"id":str(role.id),"name":role.name,"kind":role.kind,"capacity_fte":str(role.capacity_fte),"sales_rate":str(role.sales_rate),"lock_version":role.lock_version}

@router.delete("/rate-card-roles/{role_id}")
def delete_rate_role(role_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    role=db.get(RateCardRole,role_id)
    if not role:raise HTTPException(404,"Rolle nicht gefunden")
    from kusys.persistence.models import RateCard
    card=db.get(RateCard,role.rate_card_id)
    if not card or not card.project_id:raise HTTPException(422,"Firmenvorlage kann hier nicht geändert werden")
    require_project_access(db,actor,card.project_id,{"project_lead","company_admin"})
    used=db.scalar(select(WPModel.id).where(WPModel.project_id==card.project_id,WPModel.role_name==role.name,WPModel.deleted_at.is_(None)).limit(1))
    if used:raise HTTPException(409,"Rolle wird von Arbeitspaketen verwendet")
    db.delete(role);db.commit();return {"status":"deleted"}

@router.delete("/work-package-dependencies/{dependency_id}")
def delete_dependency(dependency_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    dep=db.get(WorkPackageDependency,dependency_id)
    if not dep:raise HTTPException(404,"Abhängigkeit nicht gefunden")
    wp=db.get(WPModel,dep.successor_id)
    if not wp:raise HTTPException(404,"Arbeitspaket nicht gefunden")
    require_project_access(db,actor,wp.project_id,{"project_lead","project_member","company_admin"});dep.active=False;db.commit();return {"status":"inactive"}

@router.get("/projects/{project_id}/risk-suggestion")
def risk_suggestion(project_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_project_access(db,actor,project_id)
    rows=list(db.scalars(select(WPModel).where(WPModel.project_id==project_id,WPModel.deleted_at.is_(None))))
    plan=sum(x.plan_hours for x in rows)
    if plan<=0:return {"risk_percent":0,"calculable":False,"expected_hours":0,"spread_hours":0}
    expected=sum((x.min_hours+4*x.likely_hours+x.max_hours)/6 for x in rows)
    spread=sum((x.max_hours-x.min_hours)/6 for x in rows)
    suggested=max(0,round((expected+spread)/plan*100-100))
    return {"risk_percent":suggested,"calculable":True,"expected_hours":round(expected,2),"spread_hours":round(spread,2),"plan_hours":plan}


@router.get("/tenants/{tenant_id}/rate-card")
def tenant_rate_card(tenant_id:uuid.UUID,db:Session=Depends(get_db),actor:Actor=Depends(require_actor)):
    require_tenant_access(db,actor,tenant_id,{"company_admin"})
    card=ensure_tenant_rate_card(db,tenant_id,actor.user.id);db.commit()
    roles=list(db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id==card.id).order_by(RateCardRole.name)))
    return {"id":str(card.id),"name":card.name,"lock_version":card.lock_version,"roles":[{"id":str(x.id),"name":x.name,"aliases":x.aliases,"kind":x.kind,"capacity_fte":str(x.capacity_fte),"internal_cost_rate":str(x.internal_cost_rate) if x.internal_cost_rate is not None else None,"purchase_rate":str(x.purchase_rate) if x.purchase_rate is not None else None,"markup_percent":str(x.markup_percent) if x.markup_percent is not None else None,"sales_rate":str(x.sales_rate),"lock_version":x.lock_version} for x in roles]}

class RateCardReload(BaseModel):
    apply: bool = False

@router.post("/projects/{project_id}/rate-card/reload-template")
def reload_rate_card(project_id:uuid.UUID,payload:RateCardReload,db:Session=Depends(get_db),actor:Actor=Depends(require_csrf)):
    require_project_access(db,actor,project_id,{"project_lead","company_admin"});p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Projekt nicht gefunden")
    card=ensure_project_rate_card(db,p,actor.user.id);template=ensure_tenant_rate_card(db,p.tenant_id,actor.user.id)
    current={x.name:x for x in db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id==card.id))}
    source={x.name:x for x in db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id==template.id))}
    diffs=[]
    for name in sorted(set(current)|set(source)):
        c,t=current.get(name),source.get(name)
        before=None if not c else {"kind":c.kind,"capacity_fte":str(c.capacity_fte),"internal_cost_rate":str(c.internal_cost_rate) if c.internal_cost_rate is not None else None,"purchase_rate":str(c.purchase_rate) if c.purchase_rate is not None else None,"markup_percent":str(c.markup_percent) if c.markup_percent is not None else None,"sales_rate":str(c.sales_rate)}
        after=None if not t else {"kind":t.kind,"capacity_fte":str(t.capacity_fte),"internal_cost_rate":str(t.internal_cost_rate) if t.internal_cost_rate is not None else None,"purchase_rate":str(t.purchase_rate) if t.purchase_rate is not None else None,"markup_percent":str(t.markup_percent) if t.markup_percent is not None else None,"sales_rate":str(t.sales_rate)}
        if before!=after: diffs.append({"role":name,"project":before,"template":after})
    if payload.apply:
        used=set(db.scalars(select(WPModel.role_name).where(WPModel.project_id==project_id,WPModel.deleted_at.is_(None))))
        # Existing roles used in project work packages are not silently deleted; all updates remain explicit/diffable.
        for name,t in source.items():
            c=current.get(name)
            if c:
                c.aliases=list(t.aliases or []);c.kind=t.kind;c.capacity_fte=t.capacity_fte;c.internal_cost_rate=t.internal_cost_rate;c.purchase_rate=t.purchase_rate;c.markup_percent=t.markup_percent;c.sales_rate=t.sales_rate;bump_version(c)
            else:
                db.add(RateCardRole(rate_card_id=card.id,name=t.name,aliases=list(t.aliases or []),kind=t.kind,capacity_fte=t.capacity_fte,internal_cost_rate=t.internal_cost_rate,purchase_rate=t.purchase_rate,markup_percent=t.markup_percent,sales_rate=t.sales_rate,created_by=actor.user.id))
        for name,c in current.items():
            if name not in source and name not in used: db.delete(c)
        card.source_rate_card_id=template.id;bump_version(card);db.commit()
    return {"template_id":str(template.id),"project_rate_card_id":str(card.id),"diff":diffs,"applied":payload.apply}
