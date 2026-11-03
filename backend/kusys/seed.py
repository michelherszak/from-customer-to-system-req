from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import create_user
from kusys.persistence.models import (
    Customer, DocumentTemplate, DocumentTemplateVersion, Project, ProjectMembership, Tenant, TenantMembership,
)
from kusys.services.calculation import ensure_calendar, ensure_project_rate_card

DEMO_PASSWORD="KuSys-Demo-2026"


def seed_demo(db:Session)->dict:
    tenant=db.scalar(select(Tenant).where(Tenant.name=="VAZA Demo Engineering GmbH"))
    if not tenant:
        tenant=Tenant(name="VAZA Demo Engineering GmbH",address="Beispielweg 12, 10115 Berlin, Deutschland",country="DE",email="sophie.schneider@example.com",phone="+49 30 000000-10",contact_name="Sophie Schneider",vat_id="DE000000000",currency="EUR",language="de",timezone="Europe/Berlin")
        db.add(tenant);db.flush()
    users={}
    for username,name,email,role in [
        ("sophie.schneider","Sophie Schneider","sophie.schneider@example.com","company_admin"),
        ("max.mustermann","Max Mustermann","max.mustermann@example.com","project_lead"),
        ("lea.pruefer","Lea Prüfer","lea.pruefer@example.com","project_lead"),
        ("tom.mitglied","Tom Mitglied","tom.mitglied@example.com","project_member"),
        ("kunde.nordstern","Anna Becker","anna.becker@example.org","customer"),
    ]:
        from kusys.persistence.models import User
        u=db.scalar(select(User).where(User.username==username))
        if not u:u=create_user(db,username,name,DEMO_PASSWORD,email)
        users[username]=u
        if not db.scalar(select(TenantMembership).where(TenantMembership.tenant_id==tenant.id,TenantMembership.user_id==u.id)):
            db.add(TenantMembership(tenant_id=tenant.id,user_id=u.id,role=role,created_by=u.id))
    from kusys.persistence.models import User
    platform_admin=db.scalar(select(User).where(User.username=="platform.admin"))
    if not platform_admin:
        platform_admin=create_user(db,"platform.admin","Plattform Admin",DEMO_PASSWORD,"platform.admin@example.com",is_platform_admin=True)
    users["platform.admin"]=platform_admin
    customer=db.scalar(select(Customer).where(Customer.tenant_id==tenant.id,Customer.customer_number=="KD-10001"))
    if not customer:
        customer=Customer(tenant_id=tenant.id,customer_number="KD-10001",company_name="Nordstern Verpackungstechnik GmbH",address="Hafenallee 25, 20457 Hamburg",country="DE",contact_name="Anna Becker",department="Technischer Einkauf",email="anna.becker@example.org",phone="+49 40 000000-20",created_by=users["sophie.schneider"].id);db.add(customer);db.flush()
    project=db.scalar(select(Project).where(Project.tenant_id==tenant.id,Project.project_number=="PRJ-2026-0001"))
    if not project:
        project=Project(tenant_id=tenant.id,project_number="PRJ-2026-0001",name="PX-2400 – Modernisierung Verpackungslinie",short_description="Synthetisches Demo-Projekt für den vollständigen KuSys-Durchstich",customer_id=customer.id,customer_contact="Anna Becker",owner_user_id=users["max.mustermann"].id,status="active",document_language="de",planned_start=date(2026,10,1),created_by=users["sophie.schneider"].id);db.add(project);db.flush()
    for username,role in [("max.mustermann","project_lead"),("lea.pruefer","project_lead"),("tom.mitglied","project_member"),("kunde.nordstern","customer")]:
        u=users[username]
        if not db.scalar(select(ProjectMembership).where(ProjectMembership.project_id==project.id,ProjectMembership.user_id==u.id)):
            db.add(ProjectMembership(project_id=project.id,user_id=u.id,role=role,created_by=users["sophie.schneider"].id))
    ensure_project_rate_card(db,project,users["sophie.schneider"].id);ensure_calendar(db,project,users["sophie.schneider"].id)
    template=db.scalar(select(DocumentTemplate).where(DocumentTemplate.tenant_id==tenant.id,DocumentTemplate.name=="Standardangebot"))
    if not template:
        template=DocumentTemplate(tenant_id=tenant.id,name="Standardangebot",kind="offer",created_by=users["sophie.schneider"].id);db.add(template);db.flush()
        db.add(DocumentTemplateVersion(template_id=template.id,version=1,status="veröffentlicht",config_json={"page_size":"A4","margins_mm":[20,20,20,20],"show_hours":False},content_blocks=[{"type":"system","placeholder":"requirements","required":True},{"type":"system","placeholder":"payment_plan","required":True}],created_by=users["sophie.schneider"].id))
    db.commit()
    return {"tenant_id":str(tenant.id),"project_id":str(project.id),"users":["sophie.schneider","max.mustermann","lea.pruefer","tom.mitglied","kunde.nordstern","platform.admin"],"password":DEMO_PASSWORD}

if __name__=="__main__":
    from kusys.persistence.database import SessionLocal
    with SessionLocal() as db:print(seed_demo(db))
