from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kusys.common.money import money, pct
from kusys.requirements.domain import RequirementAttribution


@dataclass(frozen=True, slots=True)
class Rate:
    role: str
    cost_per_hour: Decimal
    sales_per_hour: Decimal


@dataclass(frozen=True, slots=True)
class PricedWorkPackage:
    id: str
    role: str
    hours: int
    requirement_ids: tuple[str, ...]
    weights: tuple[Decimal, ...] | None = None
    scaling_mode: str = "proportional"


@dataclass(frozen=True, slots=True)
class MaterialItem:
    id: str
    cost_eur: Decimal
    sales_eur: Decimal
    requirement_ids: tuple[str, ...] = ()
    scaling_mode: str = "proportional"


@dataclass(frozen=True, slots=True)
class PricingResult:
    labor_cost_eur: Decimal
    labor_sales_eur: Decimal
    material_cost_eur: Decimal
    material_sales_eur: Decimal
    risk_eur: Decimal
    discount_eur: Decimal
    net_eur: Decimal
    vat_eur: Decimal
    gross_eur: Decimal
    margin_eur: Decimal
    attribution: tuple[RequirementAttribution, ...]


class PricingEngine:
    def calculate(
        self,
        work_packages: list[PricedWorkPackage],
        rates: list[Rate],
        materials: list[MaterialItem],
        requirement_budgets: dict[str, Decimal | None],
        risk_percent: Decimal = Decimal("0"),
        discount_percent: Decimal = Decimal("0"),
        vat_percent: Decimal = Decimal("19"),
    ) -> PricingResult:
        rate_map = {r.role: r for r in rates}
        labor_cost = Decimal("0")
        labor_sales = Decimal("0")
        cost_attr: dict[str, Decimal] = {rid: Decimal("0") for rid in requirement_budgets}
        sales_attr: dict[str, Decimal] = {rid: Decimal("0") for rid in requirement_budgets}
        global_ids = tuple(sorted(requirement_budgets))

        for p in work_packages:
            if p.role not in rate_map:
                raise ValueError(f"No rate configured for role {p.role}")
            rate = rate_map[p.role]
            pcost = money(rate.cost_per_hour * p.hours)
            psales = money(rate.sales_per_hour * p.hours)
            labor_cost += pcost
            labor_sales += psales
            ids = p.requirement_ids or global_ids
            self._split(pcost, ids, p.weights if p.requirement_ids else None, cost_attr)
            self._split(psales, ids, p.weights if p.requirement_ids else None, sales_attr)

        material_cost = sum((money(m.cost_eur) for m in materials), Decimal("0"))
        material_sales = sum((money(m.sales_eur) for m in materials), Decimal("0"))
        for m in materials:
            ids = m.requirement_ids or global_ids
            self._split(money(m.cost_eur), ids, None, cost_attr)
            self._split(money(m.sales_eur), ids, None, sales_attr)

        base_sales = money(labor_sales + material_sales)
        risk = money(base_sales * pct(risk_percent))
        before_discount = money(base_sales + risk)
        discount = money(before_discount * pct(discount_percent))
        net = money(before_discount - discount)
        vat = money(net * pct(vat_percent))
        gross = money(net + vat)
        total_cost = money(labor_cost + material_cost)
        margin = money(net - total_cost)

        # Offer-level risk and discount are allocated proportionally to requirements so the
        # sum of requirement sales attribution reconciles exactly to authoritative offer net.
        if base_sales and sales_attr:
            factor = net / base_sales
            scaled = {rid: money(value * factor) for rid, value in sales_attr.items()}
            diff = money(net - sum(scaled.values(), Decimal("0")))
            if diff and scaled:
                target_id = max(scaled, key=lambda rid: abs(scaled[rid]))
                scaled[target_id] = money(scaled[target_id] + diff)
            sales_attr = scaled

        attribution = []
        for rid in sorted(requirement_budgets):
            c = money(cost_attr.get(rid, 0))
            s = money(sales_attr.get(rid, 0))
            budget = requirement_budgets[rid]
            attribution.append(
                RequirementAttribution(
                    requirement_id=rid,
                    cost_eur=c,
                    sales_eur=s,
                    margin_eur=money(s - c),
                    budget_delta_eur=None if budget is None else money(Decimal(budget) - s),
                )
            )
        return PricingResult(
            labor_cost_eur=money(labor_cost), labor_sales_eur=money(labor_sales),
            material_cost_eur=money(material_cost), material_sales_eur=money(material_sales),
            risk_eur=risk, discount_eur=discount, net_eur=net, vat_eur=vat, gross_eur=gross,
            margin_eur=margin, attribution=tuple(attribution),
        )

    @staticmethod
    def _split(amount: Decimal, requirement_ids: tuple[str, ...], weights: tuple[Decimal, ...] | None, target: dict[str, Decimal]) -> None:
        if not requirement_ids:
            return
        if weights is not None and len(weights) != len(requirement_ids):
            raise ValueError("weights must match requirement_ids")
        if weights is None:
            weights = tuple(Decimal("1") for _ in requirement_ids)
        total = sum(weights, Decimal("0"))
        if total <= 0:
            raise ValueError("weight sum must be > 0")
        allocations = [money(amount * weight / total) for weight in weights]
        diff = money(amount - sum(allocations, Decimal("0")))
        if diff:
            idx = max(range(len(allocations)), key=lambda i: abs(allocations[i]))
            allocations[idx] = money(allocations[idx] + diff)
        for rid, part in zip(requirement_ids, allocations, strict=True):
            target[rid] = target.get(rid, Decimal("0")) + part
