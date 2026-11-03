from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil


@dataclass(frozen=True, slots=True)
class WorkPackage:
    id: str
    name: str
    role: str
    hours: int
    predecessors: tuple[str, ...] = ()
    max_fte: float = 1.0
    priority: int = 3
    requirement_ids: tuple[str, ...] = ()
    scaling_mode: str = "proportional"


@dataclass(frozen=True, slots=True)
class RoleCapacity:
    role: str
    fte: float


@dataclass(frozen=True, slots=True)
class ScheduledPackage:
    id: str
    start: date
    finish: date
    duration_days: int
    total_float_days: int
    critical: bool


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    packages: tuple[ScheduledPackage, ...]
    project_finish: date
    critical_path: tuple[str, ...]


class PlanningError(ValueError):
    pass


def _is_workday(day: date, holidays: set[date], weekdays: set[int]) -> bool:
    return day.weekday() in weekdays and day not in holidays


def _next_workday(day: date, holidays: set[date], weekdays: set[int]) -> date:
    while not _is_workday(day, holidays, weekdays):
        day += timedelta(days=1)
    return day


def _previous_workday(day: date, holidays: set[date], weekdays: set[int]) -> date:
    while not _is_workday(day, holidays, weekdays):
        day -= timedelta(days=1)
    return day


def _add_workdays(start: date, duration: int, holidays: set[date], weekdays: set[int]) -> date:
    if duration <= 1:
        return _next_workday(start, holidays, weekdays)
    day = _next_workday(start, holidays, weekdays)
    left = duration - 1
    while left:
        day += timedelta(days=1)
        if _is_workday(day, holidays, weekdays):
            left -= 1
    return day


def _subtract_workdays(finish: date, duration: int, holidays: set[date], weekdays: set[int]) -> date:
    if duration <= 1:
        return _previous_workday(finish, holidays, weekdays)
    day = _previous_workday(finish, holidays, weekdays)
    left = duration - 1
    while left:
        day -= timedelta(days=1)
        if _is_workday(day, holidays, weekdays):
            left -= 1
    return day


def _workdays_between(start: date, end: date, holidays: set[date], weekdays: set[int]) -> int:
    if end < start:
        return 0
    count = 0
    day = start
    while day <= end:
        if _is_workday(day, holidays, weekdays):
            count += 1
        day += timedelta(days=1)
    return count


class PlanningEngine:
    """Deterministic CPM + renewable-resource leveling engine.

    Dependencies are finish-to-start with a one-workday separation. Resource capacity is
    allocated per role and workday. A work package may use up to ``max_fte`` and can run
    concurrently with other packages as long as the role capacity is not exceeded.
    """

    def schedule(
        self,
        packages: list[WorkPackage],
        capacities: list[RoleCapacity],
        project_start: date,
        holidays: set[date] | None = None,
        hours_per_day: int = 8,
        weekdays: set[int] | None = None,
    ) -> ScheduleResult:
        holidays = holidays or set()
        weekdays = weekdays or {0, 1, 2, 3, 4}
        if not weekdays or any(x < 0 or x > 6 for x in weekdays):
            raise PlanningError("weekdays must contain values 0-6")
        if hours_per_day <= 0:
            raise PlanningError("hours_per_day must be positive")
        by_id = {p.id: p for p in packages}
        if len(by_id) != len(packages):
            raise PlanningError("Duplicate work package IDs")
        for p in packages:
            if p.hours < 0:
                raise PlanningError(f"Negative effort for {p.id}")
            if p.max_fte <= 0:
                raise PlanningError(f"max_fte must be positive for {p.id}")
            missing = [x for x in p.predecessors if x not in by_id]
            if missing:
                raise PlanningError(f"Unknown predecessors for {p.id}: {missing}")

        if not packages:
            return ScheduleResult(packages=(), project_finish=_next_workday(project_start, holidays, weekdays), critical_path=())

        order = self._topological_order(packages)
        order_index = {pid: i for i, pid in enumerate(order)}
        successors = self._successors(packages)
        capacities_by_role = {x.role: max(0.0, x.fte) for x in capacities}
        for p in packages:
            if capacities_by_role.get(p.role, 0.0) <= 0:
                raise PlanningError(f"No positive capacity configured for role {p.role!r}")

        # CPM without resource contention. It provides stable criticality/priority input for leveling.
        ideal_duration = {
            p.id: (0 if p.hours == 0 else max(1, ceil(p.hours / (hours_per_day * min(p.max_fte, capacities_by_role[p.role])))))
            for p in packages
        }
        cpm_start: dict[str, date] = {}
        cpm_finish: dict[str, date] = {}
        for pid in order:
            p = by_id[pid]
            earliest = _next_workday(project_start, holidays, weekdays)
            if p.predecessors:
                earliest = max(_next_workday(cpm_finish[x] + timedelta(days=1), holidays, weekdays) for x in p.predecessors)
            start = _next_workday(earliest, holidays, weekdays)
            finish = start if ideal_duration[pid] == 0 else _add_workdays(start, ideal_duration[pid], holidays, weekdays)
            cpm_start[pid], cpm_finish[pid] = start, finish
        cpm_project_finish = max(cpm_finish.values())
        cpm_latest_finish: dict[str, date] = {}
        cpm_float: dict[str, int] = {}
        for pid in reversed(order):
            if not successors[pid]:
                lf = cpm_project_finish
            else:
                lf = min(_previous_workday(cpm_start[s] - timedelta(days=1), holidays, weekdays) for s in successors[pid])
            cpm_latest_finish[pid] = lf
            cpm_float[pid] = max(0, _workdays_between(cpm_finish[pid] + timedelta(days=1), lf, holidays, weekdays))

        # True renewable-resource leveling, day by day.
        remaining = {p.id: float(p.hours) for p in packages}
        completed: set[str] = set()
        started: set[str] = set()
        starts: dict[str, date] = {}
        finishes: dict[str, date] = {}
        workdays_used: dict[str, int] = {p.id: 0 for p in packages}
        day = _next_workday(project_start, holidays, weekdays)
        guard = 0
        max_guard = max(10000, sum(max(1, p.hours) for p in packages) * 4)

        while len(completed) < len(packages):
            guard += 1
            if guard > max_guard:
                raise PlanningError("Resource leveling did not converge")
            day = _next_workday(day, holidays, weekdays)

            # Zero-hour milestones complete when their predecessors have completed, on the next
            # eligible workday after the last predecessor (or project start if none).
            milestone_progress = True
            while milestone_progress:
                milestone_progress = False
                for pid in order:
                    if pid in completed or by_id[pid].hours != 0:
                        continue
                    p = by_id[pid]
                    if not all(x in completed for x in p.predecessors):
                        continue
                    eligible = _next_workday(project_start, holidays, weekdays)
                    if p.predecessors:
                        eligible = max(_next_workday(finishes[x] + timedelta(days=1), holidays, weekdays) for x in p.predecessors)
                    if eligible <= day:
                        starts[pid] = eligible
                        finishes[pid] = eligible
                        completed.add(pid)
                        milestone_progress = True

            ready: list[str] = []
            for pid in order:
                if pid in completed or remaining[pid] <= 0:
                    continue
                p = by_id[pid]
                if not all(x in completed for x in p.predecessors):
                    continue
                if p.predecessors and any(_next_workday(finishes[x] + timedelta(days=1), holidays, weekdays) > day for x in p.predecessors):
                    continue
                ready.append(pid)

            # Dependency criticality first, then user planning priority and stable order/id.
            ready.sort(key=lambda pid: (cpm_float[pid], -by_id[pid].priority, order_index[pid], pid))
            available = dict(capacities_by_role)
            allocated_any = False
            for pid in ready:
                p = by_id[pid]
                fte = min(p.max_fte, available.get(p.role, 0.0))
                if fte <= 1e-9:
                    continue
                allocated_any = True
                started.add(pid)
                starts.setdefault(pid, day)
                workdays_used[pid] += 1
                productive_hours = hours_per_day * fte
                remaining[pid] = max(0.0, remaining[pid] - productive_hours)
                available[p.role] = max(0.0, available[p.role] - fte)
                if remaining[pid] <= 1e-9:
                    finishes[pid] = day
                    completed.add(pid)

            if len(completed) == len(packages):
                break

            # Advancing one calendar day is deterministic; _next_workday skips weekends/holidays.
            # If nothing could run because future dependency dates gate all work, advancing is still
            # correct. If a positive-capacity role is configured, lack of allocation cannot deadlock.
            day += timedelta(days=1)

        project_finish = max(finishes.values(), default=_next_workday(project_start, holidays, weekdays))

        # Backward pass over the *leveled* durations. This reflects dependency slack after resource
        # leveling. Packages finishing the leveled project are always critical; logical CPM-critical
        # packages remain critical even when resource contention lengthens the plan.
        latest_finish: dict[str, date] = {}
        total_float: dict[str, int] = {}
        for pid in reversed(order):
            if not successors[pid]:
                lf = project_finish
            else:
                lf = min(_previous_workday(starts[s] - timedelta(days=1), holidays, weekdays) for s in successors[pid])
            latest_finish[pid] = lf
            total_float[pid] = max(0, _workdays_between(finishes[pid] + timedelta(days=1), lf, holidays, weekdays))

        scheduled = tuple(
            ScheduledPackage(
                id=pid,
                start=starts[pid],
                finish=finishes[pid],
                duration_days=workdays_used[pid],
                total_float_days=total_float[pid],
                critical=(total_float[pid] == 0 or cpm_float[pid] == 0 or finishes[pid] == project_finish),
            )
            for pid in order
        )
        return ScheduleResult(
            packages=scheduled,
            project_finish=project_finish,
            critical_path=tuple(p.id for p in scheduled if p.critical),
        )

    @staticmethod
    def _successors(packages: list[WorkPackage]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {p.id: [] for p in packages}
        for p in packages:
            for pred in p.predecessors:
                result[pred].append(p.id)
        return result

    @staticmethod
    def _topological_order(packages: list[WorkPackage]) -> list[str]:
        indegree = {p.id: len(p.predecessors) for p in packages}
        successors = PlanningEngine._successors(packages)
        priorities = {p.id: p.priority for p in packages}
        ready = sorted((x for x, n in indegree.items() if n == 0), key=lambda x: (-priorities[x], x))
        result: list[str] = []
        while ready:
            current = ready.pop(0)
            result.append(current)
            for nxt in successors[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
                    ready.sort(key=lambda x: (-priorities[x], x))
        if len(result) != len(packages):
            raise PlanningError("Dependency cycle detected")
        return result
