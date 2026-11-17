"""Cost/time scenarios use existing deterministic engines and configured project data."""
from dataclasses import asdict
from decimal import Decimal
from kusys.planning.engine import PlanningEngine, PlanningError, WorkPackage
from kusys.services.calculation import load_calculation_inputs


def add_estimates(db, project_id, result):
    project, _, _, _, rates, capacities, _, _, start, holidays, hpd, weekdays = load_calculation_inputs(db, project_id)
    rate_map = {x.role: x for x in rates}
    missing = sorted({x["role"] for x in result["work_packages"]} - set(rate_map))
    scenarios = {}
    for label, field in (("minimum", "min_hours"), ("likely", "likely_hours"), ("maximum", "max_hours")):
        packages = [WorkPackage(x["key"], x["name"], x["role"], x[field], tuple(x["depends_on"])) for x in result["work_packages"]]
        scenario = {"hours": sum(x.hours for x in packages), "labor_cost_eur": None, "labor_sales_eur": None, "project_finish": None}
        if not missing:
            scenario["labor_cost_eur"] = str(sum((rate_map[x.role].cost_per_hour * Decimal(x.hours) for x in packages), Decimal(0)).quantize(Decimal(".01")))
            scenario["labor_sales_eur"] = str(sum((rate_map[x.role].sales_per_hour * Decimal(x.hours) for x in packages), Decimal(0)).quantize(Decimal(".01")))
        try:
            plan = PlanningEngine().schedule(packages, capacities, start, holidays, hpd, weekdays)
            scenario["project_finish"] = plan.project_finish.isoformat()
            scenario["packages"] = [{**asdict(x), "start": x.start.isoformat(), "finish": x.finish.isoformat()} for x in plan.packages]
        except (PlanningError, ValueError) as exc:
            scenario["schedule_error"] = str(exc)
        scenarios[label] = scenario
    result["estimate_summary"].update({"scenarios": scenarios, "planned_start": start.isoformat(), "start_basis": "Projektstart" if project.planned_start else "Berechnungsdatum (kein Projektstart hinterlegt)", "rate_snapshot": [{"role": x.role, "cost_per_hour_eur": str(x.cost_per_hour), "sales_per_hour_eur": str(x.sales_per_hour)} for x in rates], "capacity_snapshot": [asdict(x) for x in capacities], "calendar_snapshot": {"hours_per_day": hpd, "weekdays": sorted(weekdays), "holidays": sorted(x.isoformat() for x in holidays)}, "excluded": "Nur Arbeitskosten; Sachpositionen, Steuern, Risikoaufschläge und Rabatte sind nicht enthalten."})
    if missing:
        result["quality"]["status"] = "blocked"
        result["quality"]["findings"].append({"target_key": "PLAN", "owner": "work_planner", "verdict": "blocked", "origin": "code_gate", "question": "Fehlende Rate-Card-Rollen: " + ", ".join(missing)})
