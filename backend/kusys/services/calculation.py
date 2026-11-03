from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.persistence.models import (
    Holiday as HolidayModel, MaterialItem as MaterialModel, Project, RateCard, RateCardRole,
    Requirement as RequirementModel, RequirementRelation as RelationModel,
    WorkCalendar, WorkPackage as WorkPackageModel, WorkPackageDependency, WorkPackageRequirement,
)
from kusys.planning.engine import RoleCapacity, WorkPackage
from kusys.pricing.engine import MaterialItem, PricedWorkPackage, Rate
from kusys.requirements.domain import Priority, RelationType, Requirement, RequirementGraph, RequirementRelation

DEFAULT_ROLES = {
    "Systems Engineering": (Decimal("75"), Decimal("125"), Decimal("2")),
    "Software Engineering": (Decimal("80"), Decimal("135"), Decimal("2")),
    "Electrical Engineering": (Decimal("78"), Decimal("130"), Decimal("1")),
    "Mechanical Engineering": (Decimal("76"), Decimal("128"), Decimal("1")),
    "Safety Engineering": (Decimal("90"), Decimal("150"), Decimal("0.5")),
    "Security Engineering": (Decimal("95"), Decimal("160"), Decimal("0.5")),
    "Test Engineering": (Decimal("70"), Decimal("118"), Decimal("1.5")),
    "Documentation": (Decimal("60"), Decimal("100"), Decimal("1")),
}


def ensure_tenant_rate_card(db: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> RateCard:
    card = db.scalar(select(RateCard).where(RateCard.tenant_id == tenant_id, RateCard.project_id.is_(None), RateCard.active.is_(True)))
    if card:
        return card
    card = RateCard(tenant_id=tenant_id, project_id=None, name="Firmen-Rate-Card", created_by=actor_id)
    db.add(card); db.flush()
    for name, (cost, sales, fte) in DEFAULT_ROLES.items():
        db.add(RateCardRole(rate_card_id=card.id, name=name, kind="internal", capacity_fte=fte, internal_cost_rate=cost, sales_rate=sales, created_by=actor_id))
    db.flush()
    return card


def ensure_project_rate_card(db: Session, project: Project, actor_id: uuid.UUID | None = None) -> RateCard:
    card = db.scalar(select(RateCard).where(RateCard.project_id == project.id, RateCard.active.is_(True)))
    if card:
        return card
    template = ensure_tenant_rate_card(db, project.tenant_id, actor_id)
    card = RateCard(tenant_id=project.tenant_id, project_id=project.id, name=f"Rate Card {project.project_number}", source_rate_card_id=template.id, created_by=actor_id)
    db.add(card); db.flush()
    for r in db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id == template.id).order_by(RateCardRole.name)):
        db.add(RateCardRole(rate_card_id=card.id, name=r.name, aliases=list(r.aliases or []), kind=r.kind, capacity_fte=r.capacity_fte, internal_cost_rate=r.internal_cost_rate, purchase_rate=r.purchase_rate, markup_percent=r.markup_percent, sales_rate=r.sales_rate, created_by=actor_id))
    db.flush()
    return card


def ensure_calendar(db: Session, project: Project, actor_id: uuid.UUID | None = None) -> WorkCalendar:
    cal = db.scalar(select(WorkCalendar).where(WorkCalendar.project_id == project.id))
    if cal: return cal
    cal = WorkCalendar(tenant_id=project.tenant_id, project_id=project.id, name=f"Kalender {project.project_number}", hours_per_day=8, created_by=actor_id)
    db.add(cal); db.flush(); return cal


def load_graph(db: Session, project_id: uuid.UUID, scope_ids: set[uuid.UUID] | None = None) -> tuple[RequirementGraph, dict[str, uuid.UUID]]:
    rows = list(db.scalars(select(RequirementModel).where(RequirementModel.project_id == project_id, RequirementModel.deleted_at.is_(None))))
    if scope_ids is not None:
        rows = [r for r in rows if r.id in scope_ids]
    graph = RequirementGraph(); id_map = {}
    for r in rows:
        sid = str(r.id); id_map[sid] = r.id
        try: prio = Priority(r.priority)
        except Exception: prio = Priority.SHOULD
        graph.add(Requirement(sid, r.key, r.title, r.text, prio, r.budget_eur, r.max_price_eur, True))
    valid_ids = set(graph.requirements)
    for rel in db.scalars(select(RelationModel).where(RelationModel.project_id == project_id, RelationModel.active.is_(True))):
        s, t = str(rel.source_id), str(rel.target_id)
        if s not in valid_ids or t not in valid_ids: continue
        try: rt = RelationType(rel.relation_type)
        except Exception: continue
        graph.link(RequirementRelation(s, t, rt, rel.rationale))
    return graph, id_map


def _wp_links(db: Session, project_id: uuid.UUID) -> tuple[dict[uuid.UUID, list[WorkPackageRequirement]], dict[uuid.UUID, list[uuid.UUID]]]:
    wps = list(db.scalars(select(WorkPackageModel).where(WorkPackageModel.project_id == project_id, WorkPackageModel.deleted_at.is_(None))))
    wp_ids = [x.id for x in wps]
    links = list(db.scalars(select(WorkPackageRequirement).where(WorkPackageRequirement.work_package_id.in_(wp_ids)))) if wp_ids else []
    by_wp: dict[uuid.UUID, list[WorkPackageRequirement]] = {wid: [] for wid in wp_ids}
    for link in links: by_wp.setdefault(link.work_package_id, []).append(link)
    deps = list(db.scalars(select(WorkPackageDependency).where(WorkPackageDependency.successor_id.in_(wp_ids), WorkPackageDependency.active.is_(True)))) if wp_ids else []
    pred: dict[uuid.UUID, list[uuid.UUID]] = {wid: [] for wid in wp_ids}
    for d in deps: pred.setdefault(d.successor_id, []).append(d.predecessor_id)
    return by_wp, pred


def load_calculation_inputs(db: Session, project_id: uuid.UUID, scope_ids: set[uuid.UUID] | None = None):
    project = db.get(Project, project_id)
    if not project: raise ValueError("Projekt nicht gefunden")
    card = ensure_project_rate_card(db, project)
    calendar = ensure_calendar(db, project)
    roles = list(db.scalars(select(RateCardRole).where(RateCardRole.rate_card_id == card.id)))
    rates = [Rate(r.name, Decimal(r.internal_cost_rate or r.purchase_rate or 0), Decimal(r.sales_rate)) for r in roles]
    capacities = [RoleCapacity(r.name, float(r.capacity_fte)) for r in roles]
    graph, _ = load_graph(db, project_id, scope_ids)
    active_req_str = set(graph.requirements)
    req_uuid = {uuid.UUID(x) for x in active_req_str}
    by_wp, pred = _wp_links(db, project_id)
    plan_packages=[]; priced=[]
    source_rows = list(db.scalars(select(WorkPackageModel).where(WorkPackageModel.project_id == project_id, WorkPackageModel.deleted_at.is_(None)).order_by(WorkPackageModel.key)))
    included_wp_ids: set[uuid.UUID] = set()
    prepared: list[tuple[WorkPackageModel, int, tuple[str, ...], tuple[Decimal, ...] | None]] = []
    for wp in source_rows:
        links = by_wp.get(wp.id, [])
        selected_links = [x for x in links if x.requirement_id in req_uuid]
        selected_req = tuple(str(x.requirement_id) for x in selected_links)
        if links and not selected_req and not wp.global_package:
            continue
        if links and wp.scaling_mode == "proportional":
            fraction = Decimal(len(selected_req)) / Decimal(len(links))
            hours = int((Decimal(wp.plan_hours) * fraction).quantize(Decimal("1")))
            if fraction > 0 and wp.plan_hours > 0:
                hours = max(1, hours)
        else:
            hours = wp.plan_hours
        weights = tuple(Decimal(x.weight) if x.weight is not None else Decimal("1") for x in selected_links) if selected_links else None
        included_wp_ids.add(wp.id)
        prepared.append((wp, hours, selected_req, weights))
    for wp, hours, selected_req, weights in prepared:
        # Dependencies to packages that are not part of this offer view are omitted from the
        # derived schedule; the master-plan dependency itself remains unchanged in persistence.
        predecessors = tuple(str(x) for x in pred.get(wp.id, []) if x in included_wp_ids)
        plan_packages.append(WorkPackage(str(wp.id), wp.name, wp.role_name, hours, predecessors, float(wp.max_fte), wp.planning_priority, selected_req, wp.scaling_mode))
        priced.append(PricedWorkPackage(str(wp.id), wp.role_name, hours, selected_req, weights, wp.scaling_mode))
    materials=[]
    for m in db.scalars(select(MaterialModel).where(MaterialModel.project_id == project_id, MaterialModel.deleted_at.is_(None))):
        all_ids = [str(x) for x in (m.requirement_ids or [])]
        selected = tuple(x for x in all_ids if x in active_req_str)
        if all_ids and not selected: continue
        factor = Decimal(len(selected))/Decimal(len(all_ids)) if all_ids and m.scaling_mode == "proportional" else Decimal("1")
        materials.append(MaterialItem(str(m.id), Decimal(m.cost_eur)*factor, Decimal(m.sales_eur)*factor, selected, m.scaling_mode))
    budgets = {rid: graph.requirements[rid].budget_eur for rid in graph.requirements}
    holidays = set(db.scalars(select(HolidayModel.day).where(HolidayModel.calendar_id == calendar.id)))
    start = project.planned_start or date.today()
    return project, graph, plan_packages, priced, rates, capacities, materials, budgets, start, holidays, calendar.hours_per_day, set(calendar.weekdays or [0,1,2,3,4])
