from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from kusys.common.security import utcnow
from kusys.persistence.models import (
    Baseline, BaselineRequirement, ClarificationItem, Customer, DocumentTemplateVersion, MaterialItem,
    Offer, OfferPosition, OfferScopeItem, OfferSnapshot, OfferTextBlock, OfferVersion, Project, RateCard, RateCardRole, Requirement,
    RequirementCostAttribution, WorkPackage, WorkPackageRequirement,
)
from kusys.planning.engine import PlanningEngine
from kusys.pricing.engine import PricingEngine
from kusys.services.calculation import load_calculation_inputs

STATUS_FLOW = {
    "Entwurf": {"zur Freigabe"},
    "zur Freigabe": {"Entwurf", "freigegeben"},
    "freigegeben": {"versendet"},
    "versendet": {"angenommen", "abgelehnt"},
    "angenommen": set(),
    "abgelehnt": set(),
}


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def create_baseline_for_offer(db: Session, project: Project, actor_id: uuid.UUID, name: str) -> Baseline:
    reqs = list(db.scalars(select(Requirement).where(Requirement.project_id == project.id, Requirement.deleted_at.is_(None)).order_by(Requirement.key)))
    items = [{
        "id": str(r.id), "key": r.key, "title": r.title, "text": r.text, "priority": r.priority,
        "revision": r.business_revision, "source_refs": r.source_refs, "origin": r.origin,
        "budget_eur": str(r.budget_eur) if r.budget_eur is not None else None,
    } for r in reqs]
    snapshot = {"project_id": str(project.id), "requirements": items}
    checksum = hashlib.sha256(canonical(snapshot)).hexdigest()
    b = Baseline(tenant_id=project.tenant_id, project_id=project.id, name=name, checksum=checksum, snapshot_json=snapshot, created_by=actor_id)
    db.add(b); db.flush()
    for r, item in zip(reqs, items, strict=True):
        db.add(BaselineRequirement(baseline_id=b.id, requirement_id=r.id, requirement_revision=r.business_revision, snapshot_json=item, created_by=actor_id))
    return b


def scope_ids(db: Session, version: OfferVersion) -> set[uuid.UUID]:
    return set(db.scalars(select(OfferScopeItem.requirement_id).where(OfferScopeItem.offer_version_id == version.id, OfferScopeItem.included.is_(True))))


def preview(db: Session, version: OfferVersion) -> dict:
    offer = db.get(Offer, version.offer_id)
    project = db.get(Project, offer.project_id)
    included = scope_ids(db, version)
    _, graph, wps, priced, rates, capacities, materials, budgets, start, holidays, hpd, weekdays = load_calculation_inputs(db, project.id, included)
    schedule = PlanningEngine().schedule(wps, capacities, start, holidays, hpd, weekdays)
    pricing = PricingEngine().calculate(priced, rates, materials, budgets, Decimal(version.risk_percent), Decimal(version.discount_percent), Decimal(version.vat_percent))
    req_rows = {str(r.id): r for r in db.scalars(select(Requirement).where(Requirement.project_id == project.id, Requirement.id.in_(included)))} if included else {}
    attribution = []
    for a in pricing.attribution:
        r = req_rows.get(a.requirement_id)
        attribution.append({
            "requirement_id": a.requirement_id,
            "key": r.key if r else None,
            "title": r.title if r else None,
            "budget_eur": str(r.budget_eur) if r and r.budget_eur is not None else None,
            "cost_eur": str(a.cost_eur), "sales_eur": str(a.sales_eur), "margin_eur": str(a.margin_eur),
            "budget_delta_eur": str(a.budget_delta_eur) if a.budget_delta_eur is not None else None,
        })
    budget_sum = sum((Decimal(r.budget_eur) for r in req_rows.values() if r.budget_eur is not None), Decimal("0"))
    budgeted_sales = sum((Decimal(x["sales_eur"]) for x in attribution if x["budget_eur"] is not None), Decimal("0"))
    included_wp_ids = {uuid.UUID(x.id) for x in wps}
    work_package_rows = []
    for wp in db.scalars(select(WorkPackage).where(WorkPackage.id.in_(included_wp_ids)).order_by(WorkPackage.key)) if included_wp_ids else []:
        links = list(db.scalars(select(WorkPackageRequirement).where(WorkPackageRequirement.work_package_id == wp.id)))
        work_package_rows.append({
            "id": str(wp.id), "key": wp.key, "name": wp.name, "description": wp.description,
            "role": wp.role_name, "plan_hours": next((x.hours for x in wps if x.id == str(wp.id)), 0),
            "phase": wp.phase, "max_fte": str(wp.max_fte), "planning_priority": wp.planning_priority,
            "scaling_mode": wp.scaling_mode,
            "requirement_ids": [str(x.requirement_id) for x in links if str(x.requirement_id) in set(graph.requirements)],
        })
    card = db.scalar(select(RateCard).where(RateCard.project_id == project.id, RateCard.active.is_(True)))
    rate_rows = []
    if card:
        for role in db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id == card.id).order_by(RateCardRole.name)):
            rate_rows.append({
                "name": role.name, "kind": role.kind, "capacity_fte": str(role.capacity_fte),
                "internal_cost_rate": str(role.internal_cost_rate) if role.internal_cost_rate is not None else None,
                "purchase_rate": str(role.purchase_rate) if role.purchase_rate is not None else None,
                "markup_percent": str(role.markup_percent) if role.markup_percent is not None else None,
                "sales_rate": str(role.sales_rate),
            })
    material_rows = []
    for m in db.scalars(select(MaterialItem).where(MaterialItem.project_id == project.id, MaterialItem.deleted_at.is_(None)).order_by(MaterialItem.key)):
        selected = [str(x) for x in (m.requirement_ids or []) if str(x) in set(graph.requirements)]
        if m.requirement_ids and not selected:
            continue
        factor = Decimal(len(selected)) / Decimal(len(m.requirement_ids)) if m.requirement_ids and m.scaling_mode == "proportional" else Decimal("1")
        material_rows.append({"id":str(m.id),"key":m.key,"description":m.description,"cost_eur":str(Decimal(m.cost_eur)*factor),"sales_eur":str(Decimal(m.sales_eur)*factor),"requirement_ids":selected,"scaling_mode":m.scaling_mode})
    clarification_rows = [{"key":c.key,"text":c.text,"answer":c.answer,"status":c.status} for c in db.scalars(select(ClarificationItem).where(ClarificationItem.project_id == project.id, ClarificationItem.deleted_at.is_(None)).order_by(ClarificationItem.key))]
    position_rows = [{"id":str(x.id),"position_no":x.position_no,"title":x.title,"description":x.description,"sales_eur":str(x.sales_eur),"customer_visible_hours":x.customer_visible_hours} for x in db.scalars(select(OfferPosition).where(OfferPosition.offer_version_id==version.id).order_by(OfferPosition.position_no))]
    text_rows = [{"id":str(x.id),"key":x.key,"content_html":x.content_html,"language":x.language} for x in db.scalars(select(OfferTextBlock).where(OfferTextBlock.offer_version_id==version.id).order_by(OfferTextBlock.key))]
    configured = version.payment_plan or [{"phase":"Konzept","percent":10},{"phase":"Spezifikation","percent":15},{"phase":"Realisierung","percent":45},{"phase":"Integration","percent":20},{"phase":"Abnahme","percent":10}]
    percentages = [(str(x.get("phase","Meilenstein")), Decimal(str(x.get("percent",0)))) for x in configured]
    payment_plan=[]; allocated=Decimal("0")
    for i,(phase,pct_value) in enumerate(percentages):
        amount=(pricing.net_eur*Decimal(pct_value)/Decimal("100")).quantize(Decimal("0.01"))
        if i == len(percentages)-1: amount=pricing.net_eur-allocated
        allocated += amount
        payment_plan.append({"phase":phase,"percent":str(pct_value),"amount_eur":str(amount)})
    template = None
    if version.template_version_id:
        tv = db.get(DocumentTemplateVersion, version.template_version_id)
        if tv:
            template = {"id":str(tv.id),"version":tv.version,"status":tv.status,"config_json":tv.config_json,"content_blocks":tv.content_blocks,"master_artifact_id":str(tv.master_artifact_id) if tv.master_artifact_id else None}
    return {
        "offer_version_id": str(version.id), "offer_number": offer.offer_number, "variant_name": offer.variant_name,
        "version": version.version, "status": version.status, "project_id": str(project.id), "project_name": project.name,
        "schedule": {"project_start": start.isoformat(), "project_finish": schedule.project_finish.isoformat(), "critical_path": list(schedule.critical_path),
                     "packages": [{"id": x.id, "start": x.start.isoformat(), "finish": x.finish.isoformat(), "duration_days": x.duration_days, "total_float_days": x.total_float_days, "critical": x.critical} for x in schedule.packages]},
        "pricing": {
            "labor_cost_eur": str(pricing.labor_cost_eur), "labor_sales_eur": str(pricing.labor_sales_eur),
            "material_cost_eur": str(pricing.material_cost_eur), "material_sales_eur": str(pricing.material_sales_eur),
            "risk_eur": str(pricing.risk_eur), "discount_eur": str(pricing.discount_eur), "net_eur": str(pricing.net_eur),
            "vat_eur": str(pricing.vat_eur), "gross_eur": str(pricing.gross_eur), "margin_eur": str(pricing.margin_eur),
            "attribution": attribution,
            "budget_summary": {"budget_sum_eur": str(budget_sum), "budgeted_sales_eur": str(budgeted_sales), "delta_eur": str(budget_sum - budgeted_sales)},
        },
        "scope_requirement_ids": [str(x) for x in sorted(included, key=str)],
        "work_packages": work_package_rows,
        "rate_card": rate_rows,
        "materials": material_rows,
        "clarifications": clarification_rows,
        "positions": position_rows,
        "text_blocks": text_rows,
        "payment_plan": payment_plan,
        "template": template,
    }


def persist_calculation(db: Session, version: OfferVersion, data: dict) -> None:
    p = data["pricing"]
    version.net_eur = Decimal(p["net_eur"]); version.gross_eur = Decimal(p["gross_eur"]); version.margin_eur = Decimal(p["margin_eur"])
    db.execute(delete(RequirementCostAttribution).where(RequirementCostAttribution.offer_version_id == version.id))
    for a in p["attribution"]:
        db.add(RequirementCostAttribution(
            offer_version_id=version.id, requirement_id=uuid.UUID(a["requirement_id"]), cost_eur=Decimal(a["cost_eur"]),
            sales_eur=Decimal(a["sales_eur"]), margin_eur=Decimal(a["margin_eur"]),
            budget_delta_eur=Decimal(a["budget_delta_eur"]) if a["budget_delta_eur"] is not None else None,
        ))


def freeze(db: Session, version: OfferVersion, actor_id: uuid.UUID) -> OfferSnapshot:
    data = preview(db, version)
    offer = db.get(Offer, version.offer_id); project = db.get(Project, offer.project_id)
    if version.baseline_id is None:
        version.baseline_id = create_baseline_for_offer(db, project, actor_id, f"Angebot {offer.offer_number} V{version.version}").id
    baseline = db.get(Baseline, version.baseline_id)
    data["baseline"] = baseline.snapshot_json
    data["baseline_checksum"] = baseline.checksum
    data["frozen_at"] = utcnow().isoformat()
    data["offer_header"] = {
        "offer_number": offer.offer_number, "variant": offer.variant_name, "offer_date": version.offer_date.isoformat(),
        "validity_days": version.validity_days, "language": version.language, "currency": version.currency,
        "recipient": version.recipient, "customer_reference": version.customer_reference, "internal_reference": version.internal_reference,
        "risk_percent": str(version.risk_percent), "discount_percent": str(version.discount_percent), "vat_percent": str(version.vat_percent),
    }
    if project.customer_id:
        customer = db.get(Customer, project.customer_id)
        if customer:
            data["customer"] = {"company_name": customer.company_name, "customer_number": customer.customer_number, "address": customer.address, "contact_name": customer.contact_name}
    checksum = hashlib.sha256(canonical(data)).hexdigest()
    snap = OfferSnapshot(offer_version_id=version.id, snapshot_json=data, checksum=checksum, created_by=actor_id)
    db.add(snap); persist_calculation(db, version, data); return snap


def clone_version(db: Session, source: OfferVersion, actor_id: uuid.UUID) -> OfferVersion:
    offer = db.get(Offer, source.offer_id)
    n = (db.scalar(select(func.max(OfferVersion.version)).where(OfferVersion.offer_id == offer.id)) or 0) + 1
    v = OfferVersion(
        offer_id=offer.id, version=n, status="Entwurf", offer_date=date.today(), validity_days=source.validity_days,
        language=source.language, currency=source.currency, risk_percent=source.risk_percent, discount_percent=source.discount_percent,
        vat_percent=source.vat_percent, template_version_id=source.template_version_id, created_by=actor_id,
    )
    db.add(v); db.flush()
    for item in db.scalars(select(OfferScopeItem).where(OfferScopeItem.offer_version_id == source.id)):
        db.add(OfferScopeItem(offer_version_id=v.id, requirement_id=item.requirement_id, included=item.included, created_by=actor_id))
    return v
