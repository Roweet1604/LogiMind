"""Shared metric calculation. Distance is always recomputed here from the
instance's distance matrix, never taken from a solver's own objective value.

Distance of a route = depot -> stops in order -> depot. Customer IDs unknown to
the instance are skipped for distance (the validator already flags them).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.evaluation.validator import (
    CAPACITY_EXCEEDED, TIME_VIOLATIONS, ValidationResult, route_schedule,
)
from app.models.problem import Instance


@dataclass
class Metrics:
    total_distance: float
    estimated_cost: float
    vehicles_used: int
    unserved_customers: int
    capacity_violations: int
    other_violations: int
    route_distances: list[float]
    distance_unit: str
    cost_note: str = "synthetic cost units: fixed_vehicle_cost*vehicles_used + cost_per_distance*distance"
    # Time-window metrics (all zero / empty for plain CVRP instances).
    time_window_violations: int = 0
    total_lateness: float = 0.0
    total_waiting: float = 0.0
    route_durations: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def route_distance(instance: Instance, stops: list[int]) -> float:
    idx = instance.index_of()
    nodes = [0] + [idx[c] for c in stops if c in idx and c != 0] + [0]
    if len(nodes) == 2:
        return 0.0
    m = instance.distance_matrix()
    return float(sum(m[a][b] for a, b in zip(nodes, nodes[1:])))


def compute_metrics(instance: Instance, routes: list[list[int]], validation: ValidationResult) -> Metrics:
    dists = [route_distance(instance, s) for s in routes]
    total = float(sum(dists))
    used = sum(1 for s in routes if s)
    cap_v = validation.count(CAPACITY_EXCEEDED)
    tw_v = sum(validation.count(t) for t in TIME_VIOLATIONS)
    waiting, durations = 0.0, []
    if instance.has_time_windows:
        for s in routes:
            sched = route_schedule(instance, s)
            waiting += sched.waiting
            durations.append(sched.end_time - instance.depot_ready_time if s else 0.0)
    return Metrics(
        total_distance=total,
        estimated_cost=instance.fixed_vehicle_cost * used + instance.cost_per_distance * total,
        vehicles_used=used,
        unserved_customers=len(validation.unserved),
        capacity_violations=cap_v,
        other_violations=len(validation.violations) - cap_v - tw_v - len(validation.unserved),
        route_distances=dists,
        distance_unit=instance.distance_unit,
        time_window_violations=tw_v,
        total_lateness=validation.total_lateness,
        total_waiting=waiting,
        route_durations=durations,
    )
