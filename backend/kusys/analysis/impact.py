from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import ceil

from kusys.planning.engine import PlanningEngine, RoleCapacity, WorkPackage
from kusys.pricing.engine import MaterialItem, PricedWorkPackage, PricingEngine, Rate
from kusys.requirements.domain import RequirementGraph


@dataclass(frozen=True, slots=True)
class ImpactResult:
    removed_requirement_id: str
    dependent_requirement_ids: tuple[str, ...]
    affected_work_package_ids: tuple[str, ...]
    affected_material_item_ids: tuple[str, ...]
    hours_delta: int
    cost_delta_eur: Decimal
    net_delta_eur: Decimal
    gross_delta_eur: Decimal
    margin_delta_eur: Decimal
    budget_delta_eur: Decimal
    finish_delta_days: int
    critical_path_before: tuple[str, ...]
    critical_path_after: tuple[str, ...]


class ImpactAnalysisService:
    def __init__(self) -> None:
        self.pricing = PricingEngine()
        self.planning = PlanningEngine()

    def simulate_requirement_removal(
        self,
        requirement_id: str,
        graph: RequirementGraph,
        work_packages: list[WorkPackage],
        priced_packages: list[PricedWorkPackage],
        rates: list[Rate],
        capacities: list[RoleCapacity],
        materials: list[MaterialItem],
        budgets: dict[str, Decimal | None],
        project_start,
        holidays: set | None = None,
        hours_per_day: int = 8,
        weekdays: set[int] | None = None,
    ) -> ImpactResult:
        dependents = graph.transitive_dependents(requirement_id)
        removed_scope = {requirement_id, *dependents}
        affected_ids: set[str] = set()
        remaining_wp: list[WorkPackage] = []
        remaining_priced: list[PricedWorkPackage] = []
        hours_before = sum(p.hours for p in work_packages)

        priced_map = {p.id: p for p in priced_packages}
        for p in work_packages:
            linked = tuple(p.requirement_ids)
            remaining_req = tuple(x for x in linked if x not in removed_scope)
            if linked and len(remaining_req) != len(linked):
                affected_ids.add(p.id)
            if not linked:
                new_hours = p.hours
            elif not remaining_req:
                new_hours = 0
            elif p.scaling_mode == "proportional":
                new_hours = max(1, int(round(p.hours * len(remaining_req) / len(linked)))) if p.hours > 0 else 0
            else:
                new_hours = p.hours
            if new_hours > 0 or p.hours == 0:
                remaining_wp.append(WorkPackage(
                    id=p.id, name=p.name, role=p.role, hours=new_hours, predecessors=p.predecessors,
                    max_fte=p.max_fte, priority=p.priority, requirement_ids=remaining_req,
                    scaling_mode=p.scaling_mode,
                ))
                pp = priced_map.get(p.id)
                if pp:
                    remaining_priced.append(PricedWorkPackage(
                        id=pp.id, role=pp.role, hours=new_hours, requirement_ids=remaining_req,
                        weights=None, scaling_mode=pp.scaling_mode,
                    ))

        remaining_ids = {p.id for p in remaining_wp}
        remaining_wp = [WorkPackage(
            id=p.id, name=p.name, role=p.role, hours=p.hours,
            predecessors=tuple(x for x in p.predecessors if x in remaining_ids),
            max_fte=p.max_fte, priority=p.priority, requirement_ids=p.requirement_ids,
            scaling_mode=p.scaling_mode,
        ) for p in remaining_wp]

        remaining_materials: list[MaterialItem] = []
        affected_material_ids: set[str] = set()
        for m in materials:
            linked = tuple(m.requirement_ids)
            remaining_req = tuple(x for x in linked if x not in removed_scope)
            if not linked:
                remaining_materials.append(m); continue
            if len(remaining_req) != len(linked): affected_material_ids.add(m.id)
            if not remaining_req:
                continue
            factor = Decimal(len(remaining_req)) / Decimal(len(linked)) if m.scaling_mode == "proportional" else Decimal("1")
            remaining_materials.append(MaterialItem(
                id=m.id,
                cost_eur=m.cost_eur * factor,
                sales_eur=m.sales_eur * factor,
                requirement_ids=remaining_req,
                scaling_mode=m.scaling_mode,
            ))

        before_plan = self.planning.schedule(work_packages, capacities, project_start, holidays or set(), hours_per_day, weekdays)
        after_plan = self.planning.schedule(remaining_wp, capacities, project_start, holidays or set(), hours_per_day, weekdays)
        before_price = self.pricing.calculate(priced_packages, rates, materials, budgets)
        after_price = self.pricing.calculate(remaining_priced, rates, remaining_materials, budgets)
        hours_after = sum(p.hours for p in remaining_wp)
        before_cost=before_price.labor_cost_eur+before_price.material_cost_eur
        after_cost=after_price.labor_cost_eur+after_price.material_cost_eur
        budget_before=sum((Decimal(v) for v in budgets.values() if v is not None),Decimal("0"))
        budget_after=sum((Decimal(v) for rid,v in budgets.items() if v is not None and rid not in removed_scope),Decimal("0"))
        return ImpactResult(
            removed_requirement_id=requirement_id,
            dependent_requirement_ids=tuple(sorted(dependents)),
            affected_work_package_ids=tuple(sorted(affected_ids)),
            affected_material_item_ids=tuple(sorted(affected_material_ids)),
            hours_delta=hours_after - hours_before,
            cost_delta_eur=after_cost-before_cost,
            net_delta_eur=after_price.net_eur - before_price.net_eur,
            gross_delta_eur=after_price.gross_eur - before_price.gross_eur,
            margin_delta_eur=after_price.margin_eur-before_price.margin_eur,
            budget_delta_eur=budget_after-budget_before,
            finish_delta_days=(after_plan.project_finish - before_plan.project_finish).days,
            critical_path_before=before_plan.critical_path,
            critical_path_after=after_plan.critical_path,
        )
