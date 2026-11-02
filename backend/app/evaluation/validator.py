"""Independent route validator.

It trusts nothing from the solver: it only looks at the routes (lists of
customer IDs, depot implicit at the start and end of every route) and the
instance. Same code is used for OR-Tools and the GA.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.models.problem import DEPOT_NODE, TIME_EPS, Instance

VALIDATOR_VERSION = "1.1"  # 1.1: time-window and depot-return checks

UNKNOWN_CUSTOMER = "unknown_customer"
DEPOT_AS_STOP = "depot_as_stop"
DUPLICATE_VISIT = "duplicate_visit"
UNSERVED_CUSTOMER = "unserved_customer"
CAPACITY_EXCEEDED = "capacity_exceeded"
TOO_MANY_VEHICLES = "too_many_vehicles"
TIME_WINDOW_VIOLATED = "time_window_violated"
DEPOT_RETURN_LATE = "depot_return_late"
TIME_VIOLATIONS = (TIME_WINDOW_VIOLATED, DEPOT_RETURN_LATE)


@dataclass
class RouteSchedule:
    """Timeline of one route when it leaves the depot at depot_ready_time and
    starts every service as early as allowed (waiting when early)."""
    starts: list[float]       # service start per stop
    lateness: list[float]     # max(0, start - due) per stop
    waiting: float            # total waiting before ready times
    end_time: float           # arrival back at the depot
    return_lateness: float    # max(0, end_time - depot_due_time)

    @property
    def total_lateness(self) -> float:
        return sum(self.lateness) + self.return_lateness


def route_schedule(instance: Instance, stops: list[int]) -> RouteSchedule:
    """Schedule for a route of known customer IDs (unknown IDs are skipped;
    the validator reports them separately)."""
    idx = instance.index_of()
    nodes = [idx[c] for c in stops if c in idx and c != DEPOT_NODE]
    t = instance.travel_time_matrix()
    ready, due, service = instance.ready_times, instance.due_times, instance.service_times
    now, prev, waiting = instance.depot_ready_time, 0, 0.0
    starts, lateness = [], []
    for node in nodes:
        arrival = now + t[prev][node]
        start = max(arrival, ready[node])
        waiting += start - arrival
        starts.append(start)
        lateness.append(max(0.0, start - due[node]))
        now, prev = start + service[node], node
    end = now + t[prev][0] if nodes else instance.depot_ready_time
    return RouteSchedule(starts, lateness, waiting, end, max(0.0, end - due[0]))


@dataclass
class Violation:
    type: str
    detail: str
    route_index: int | None = None


@dataclass
class ValidationResult:
    feasible: bool
    violations: list[Violation] = field(default_factory=list)
    unserved: list[int] = field(default_factory=list)
    duplicated: list[int] = field(default_factory=list)
    route_loads: list[int] = field(default_factory=list)
    total_lateness: float = 0.0
    validator_version: str = VALIDATOR_VERSION

    def count(self, violation_type: str) -> int:
        return sum(1 for v in self.violations if v.type == violation_type)

    def to_dict(self) -> dict:
        return {
            "feasible": self.feasible,
            "violations": [v.__dict__ for v in self.violations],
            "unserved": self.unserved,
            "duplicated": self.duplicated,
            "route_loads": self.route_loads,
            "total_lateness": self.total_lateness,
            "validator_version": self.validator_version,
        }


def validate_routes(instance: Instance, routes: list[list[int]]) -> ValidationResult:
    demand_of = {c.id: c.demand for c in instance.customers}
    violations: list[Violation] = []
    loads: list[int] = []
    visits: Counter[int] = Counter()

    for r, stops in enumerate(routes):
        load = 0
        for cid in stops:
            if cid == DEPOT_NODE:
                violations.append(Violation(DEPOT_AS_STOP, f"route {r} lists the depot as a customer stop", r))
                continue
            if cid not in demand_of:
                violations.append(Violation(UNKNOWN_CUSTOMER, f"route {r} visits unknown customer {cid}", r))
                continue
            visits[cid] += 1
            load += demand_of[cid]
        loads.append(load)
        if load > instance.vehicle_capacity:
            violations.append(Violation(
                CAPACITY_EXCEEDED,
                f"route {r} load {load} exceeds capacity {instance.vehicle_capacity}", r))

    duplicated = sorted(cid for cid, n in visits.items() if n > 1)
    for cid in duplicated:
        violations.append(Violation(DUPLICATE_VISIT, f"customer {cid} visited {visits[cid]} times"))

    unserved = sorted(cid for cid in demand_of if cid not in visits)
    for cid in unserved:
        violations.append(Violation(UNSERVED_CUSTOMER, f"customer {cid} is not served"))

    used = sum(1 for stops in routes if stops)
    if used > instance.vehicle_count:
        violations.append(Violation(
            TOO_MANY_VEHICLES, f"{used} non-empty routes but only {instance.vehicle_count} vehicles available"))

    total_lateness = 0.0
    if instance.has_time_windows:
        idx = instance.index_of()
        for r, stops in enumerate(routes):
            known = [c for c in stops if c in idx and c != DEPOT_NODE]
            sched = route_schedule(instance, known)
            for cid, start, late in zip(known, sched.starts, sched.lateness):
                if late > TIME_EPS:
                    total_lateness += late
                    violations.append(Violation(
                        TIME_WINDOW_VIOLATED,
                        f"route {r}: service at customer {cid} starts at {start:.2f}, "
                        f"{late:.2f} after its due time", r))
            if sched.return_lateness > TIME_EPS:
                total_lateness += sched.return_lateness
                violations.append(Violation(
                    DEPOT_RETURN_LATE,
                    f"route {r} returns to the depot at {sched.end_time:.2f}, "
                    f"{sched.return_lateness:.2f} after the depot closes", r))

    return ValidationResult(
        feasible=not violations, violations=violations, unserved=unserved,
        duplicated=duplicated, route_loads=loads, total_lateness=total_lateness)
