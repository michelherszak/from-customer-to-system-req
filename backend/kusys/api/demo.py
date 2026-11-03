from __future__ import annotations

from datetime import date
from decimal import Decimal

from kusys.analysis.impact import ImpactAnalysisService
from kusys.planning.engine import PlanningEngine, RoleCapacity, WorkPackage
from kusys.pricing.engine import MaterialItem, PricedWorkPackage, PricingEngine, Rate
from kusys.requirements.domain import Priority, RelationType, Requirement, RequirementGraph, RequirementRelation


def demo_state():
    graph = RequirementGraph()
    graph.add(Requirement("r1", "REQ-0001", "Sicherer Zugang", "Das System soll einen sicheren Zugang bereitstellen.", Priority.MUST, Decimal("18000")))
    graph.add(Requirement("r2", "REQ-0002", "Fernwartung", "Das System soll Fernwartung ermöglichen.", Priority.MUST, Decimal("12000")))
    graph.add(Requirement("r3", "REQ-0003", "Audit", "Das System soll Zugriffe protokollieren.", Priority.SHOULD, Decimal("8000")))
    graph.link(RequirementRelation("r2", "r1", RelationType.REQUIRES))
    graph.link(RequirementRelation("r3", "r2", RelationType.REQUIRES))
    wp = [
        WorkPackage("AP-001", "VPN-Gateway", "Engineering", 32, (), 1.0, 5, ("r1",)),
        WorkPackage("AP-002", "Fernwartungsservice", "Engineering", 48, ("AP-001",), 1.0, 4, ("r2",)),
        WorkPackage("AP-003", "Audit-Logging", "Software", 40, ("AP-002",), 1.0, 3, ("r3",)),
    ]
    priced = [PricedWorkPackage(p.id, p.role, p.hours, p.requirement_ids) for p in wp]
    rates = [
        Rate("Engineering", Decimal("85"), Decimal("145")),
        Rate("Software", Decimal("75"), Decimal("135")),
    ]
    capacities = [RoleCapacity("Engineering", 1.0), RoleCapacity("Software", 1.0)]
    materials = [MaterialItem("M-001", Decimal("2500"), Decimal("3900"), ("r1", "r2"))]
    budgets = {k: v.budget_eur for k, v in graph.requirements.items()}
    return graph, wp, priced, rates, capacities, materials, budgets


def demo_calculation():
    graph, wp, priced, rates, capacities, materials, budgets = demo_state()
    start = date(2026, 10, 5)
    schedule = PlanningEngine().schedule(wp, capacities, start)
    pricing = PricingEngine().calculate(priced, rates, materials, budgets, Decimal("8"), Decimal("2"), Decimal("19"))
    return graph, wp, priced, rates, capacities, materials, budgets, start, schedule, pricing
