"""Independent route validator.

It trusts nothing from the solver: it only looks at the routes (lists of
customer IDs, depot implicit at the start and end of every route) and the
instance. Same code is used for OR-Tools and the GA.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.models.problem import DEPOT_NODE, Instance

VALIDATOR_VERSION = "1.0"

UNKNOWN_CUSTOMER = "unknown_customer"
DEPOT_AS_STOP = "depot_as_stop"
DUPLICATE_VISIT = "duplicate_visit"
UNSERVED_CUSTOMER = "unserved_customer"
CAPACITY_EXCEEDED = "capacity_exceeded"
TOO_MANY_VEHICLES = "too_many_vehicles"


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

    return ValidationResult(
        feasible=not violations, violations=violations, unserved=unserved,
        duplicated=duplicated, route_loads=loads)
