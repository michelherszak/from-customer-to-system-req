from kusys.analysis.impact import ImpactAnalysisService
from kusys.api.demo import demo_calculation


def test_US14_AC_10_requirement_removal_is_non_destructive_and_transitive():
    graph, wp, priced, rates, capacities, materials, budgets, start, _, _ = demo_calculation()
    original = tuple(graph.requirements)
    impact = ImpactAnalysisService().simulate_requirement_removal(
        "r1", graph, wp, priced, rates, capacities, materials, budgets, start
    )
    assert impact.dependent_requirement_ids == ("r2", "r3")
    assert impact.hours_delta == -120
    assert tuple(graph.requirements) == original
