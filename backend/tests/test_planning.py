from datetime import date
import pytest
from kusys.planning.engine import PlanningEngine, PlanningError, RoleCapacity, WorkPackage


def test_US15_AC_06_dependency_and_critical_path():
    packages = [
        WorkPackage("A", "A", "R", 8),
        WorkPackage("B", "B", "R", 16, ("A",)),
    ]
    result = PlanningEngine().schedule(packages, [RoleCapacity("R", 1.0)], date(2026, 9, 28))
    assert result.packages[1].start > result.packages[0].finish
    assert result.critical_path == ("A", "B")


def test_US15_AC_07_cycle_is_rejected():
    packages = [WorkPackage("A", "A", "R", 8, ("B",)), WorkPackage("B", "B", "R", 8, ("A",))]
    with pytest.raises(PlanningError):
        PlanningEngine().schedule(packages, [RoleCapacity("R", 1.0)], date(2026, 9, 28))


def test_US15_AC_03_resource_leveling_uses_parallel_capacity():
    packages = [
        WorkPackage("A", "A", "R", 8),
        WorkPackage("B", "B", "R", 8),
    ]
    result = PlanningEngine().schedule(packages, [RoleCapacity("R", 2.0)], date(2026, 9, 28))
    by_id = {p.id: p for p in result.packages}
    assert by_id["A"].start == by_id["B"].start
    assert by_id["A"].finish == by_id["B"].finish


def test_US15_AC_03_resource_leveling_serializes_when_capacity_is_one_fte():
    packages = [
        WorkPackage("A", "A", "R", 8),
        WorkPackage("B", "B", "R", 8),
    ]
    result = PlanningEngine().schedule(packages, [RoleCapacity("R", 1.0)], date(2026, 9, 28))
    by_id = {p.id: p for p in result.packages}
    assert by_id["A"].finish < by_id["B"].start


def test_US15_AC_05_calendar_skips_weekends_and_holidays():
    packages = [WorkPackage("A", "A", "R", 16)]
    result = PlanningEngine().schedule(
        packages,
        [RoleCapacity("R", 1.0)],
        date(2026, 10, 2),  # Friday
        holidays={date(2026, 10, 5)},  # Monday holiday
    )
    scheduled = result.packages[0]
    assert scheduled.start == date(2026, 10, 2)
    assert scheduled.finish == date(2026, 10, 6)
