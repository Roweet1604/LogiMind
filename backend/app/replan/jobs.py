"""Turn a ReplanSetup into one guarded solver job, and the job's routes back into a per-vehicle plan.

* ortools: the timing instance with frozen prefixes, blocked vehicles and (if complete) the
  adjusted current plan as the initial assignment.
* ga (GA + local search): only when no stop is frozen, because the GA's giant-tour encoding
  cannot pin a prefix to a vehicle (decision 0012). Blocked vehicles are removed from the
  fleet (vehicles are identical), and the adjusted current plan is the GA's first tour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.replan.events import ReplanError, ReplanSetup, _with_customers
from app.selector.dataset import GA_TIME_ONLY

REPLAN_ENGINES = ("ortools", "ga")


@dataclass
class ReplanJob:
    instance: Any               # Instance the solver sees
    algorithm: str
    config: dict[str, Any]
    vehicle_map: list[int]      # solver route j -> vehicle index
    warm_start: str             # what was given as a warm start


def build_job(setup: ReplanSetup, engine: str, time_limit_s: float, warm_start: bool = True,
              seed: int = 0) -> ReplanJob:
    k = setup.instance.vehicle_count
    complete_warm = warm_start and not setup.to_insert
    if engine == "ortools":
        cfg: dict[str, Any] = {"time_limit_s": time_limit_s, "frozen": setup.frozen, "blocked": setup.blocked}
        if complete_warm:
            cfg["initial_routes"] = setup.warm_routes
        return ReplanJob(setup.timing_instance, "ortools", cfg, list(range(k)),
                         "current plan (adjusted)" if complete_warm else "none (cold start)")
    if engine != "ga":
        raise ReplanError(f"unknown replan engine {engine!r}; expected one of {REPLAN_ENGINES}")
    if setup.has_frozen:
        raise ReplanError("the GA cannot keep completed (frozen) stops in place; use engine=ortools")
    free = [v for v in range(k) if v not in setup.blocked]
    if not free:
        raise ReplanError("no vehicle left to serve the remaining stops")
    inst = _with_customers(setup.timing_instance, list(setup.timing_instance.customers), "")
    inst.vehicle_count = len(free)
    inst.instance_id = inst.compute_id()
    cfg = {**GA_TIME_ONLY, "local_search": True, "time_limit_s": time_limit_s, "seed": seed}
    if warm_start:
        tour = [c for v in free for c in setup.warm_routes[v]] + list(setup.to_insert)
        cfg["initial_tours"] = [tour]
    return ReplanJob(inst, "ga", cfg, free, "current plan (adjusted)" if warm_start else "none (cold start)")


def routes_by_vehicle(job: ReplanJob, routes: list[list[int]], vehicle_count: int) -> list[list[int]]:
    out: list[list[int]] = [[] for _ in range(vehicle_count)]
    used = [r for r in routes if r]
    if job.algorithm == "ortools":
        for v, r in enumerate(routes):
            out[v] = list(r)
        return out
    for v, r in zip(job.vehicle_map, used):
        out[v] = list(r)
    # More routes than free vehicles: keep them, so the validator reports too_many_vehicles (never hidden).
    return out + [list(r) for r in used[len(job.vehicle_map):]]
