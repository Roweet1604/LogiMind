"""Hybrid solver (P3): OR-Tools seeds the GA. Labelled "hybrid" everywhere.

Within ONE total wall-clock budget (the equal-clock rule):
1. OR-Tools runs for `ortools_share` of the budget (audited defaults for that
   sub-budget unless a strategy is given).
2. Its routes, joined into one giant tour, plus `seed_copies - 1` mutated
   copies, go into the GA's start population. The rest of the population is
   built as usual (random / nearest-neighbour / due-time tours).
3. The GA (optionally with local search) runs for whatever time is left.
Elitism keeps the seed, and the GA's split decodes the seed tour at least as
well as the OR-Tools routes, so the hybrid never ends worse than its OR-Tools
phase in the GA's own cost terms. The validator still checks the final plan.

If OR-Tools finds nothing, the GA runs unseeded and the diagnostics say so.
The standalone GA (`genetic_algorithm.py`) never calls this module.
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.evaluation.metrics import compute_metrics
from app.evaluation.validator import validate_routes
from app.models import result as R
from app.models.problem import Instance, InstanceValidationError
from app.solvers.genetic_algorithm import GAConfig, mutate, solve_ga
from app.solvers.ortools_solver import solve_ortools

MIN_GA_SECONDS = 0.05


@dataclass
class HybridConfig:
    time_limit_s: float = 10.0
    ortools_share: float = 0.5
    first_solution: str | None = None
    metaheuristic: str | None = None
    seed_copies: int = 5
    local_search: bool = True
    seed: int = 0
    ga: dict[str, Any] = field(default_factory=dict)  # other GAConfig fields

    def validate(self) -> None:
        errs = []
        if not self.time_limit_s > 0:
            errs.append("time_limit_s must be > 0")
        if not 0 < self.ortools_share < 1:
            errs.append("ortools_share must be in (0, 1)")
        if self.seed_copies < 1:
            errs.append("seed_copies must be >= 1")
        bad = set(self.ga) & {"time_limit_s", "local_search", "seed", "max_generations", "stagnation_generations"}
        if bad:
            errs.append(f"set {sorted(bad)} on the hybrid config, not inside ga")
        if errs:
            raise ValueError("; ".join(errs))


def _distance(instance: Instance, routes: list[list[int]]) -> float | None:
    v = validate_routes(instance, routes)
    return compute_metrics(instance, routes, v).total_distance if v.feasible else None


def solve_hybrid(instance: Instance, config: HybridConfig | None = None) -> R.SolveResult:
    cfg = config or HybridConfig()
    cfg_dict = asdict(cfg)

    def result(status, runtime, routes=None, message="", diag=None):
        return R.SolveResult(instance.instance_id, "hybrid", status, runtime, routes, cfg_dict,
                             seed=cfg.seed, message=message, diagnostics=diag or {})

    try:
        cfg.validate()
        GAConfig(**cfg.ga).validate()
        instance.validate()
    except (InstanceValidationError, ValueError, TypeError) as exc:
        return result(R.INVALID_INPUT, 0.0, message=str(exc))

    instance.distance_matrix()  # shared one-off cost, outside the timed region (as for both engines)
    start = time.perf_counter()
    ort = solve_ortools(instance, time_limit_s=cfg.ortools_share * cfg.time_limit_s,
                        first_solution=cfg.first_solution, metaheuristic=cfg.metaheuristic)
    ort_diag = {"status": ort.status, "runtime_seconds": ort.runtime_seconds, "message": ort.message,
                "first_solution_strategy": ort.config.get("first_solution_strategy"),
                "local_search_metaheuristic": ort.config.get("local_search_metaheuristic"),
                "seed_distance": None}
    seeds: list[list[int]] = []
    if ort.routes is not None:
        ort_diag["seed_distance"] = _distance(instance, ort.routes)
        tour = [c for r in ort.routes for c in r]
        rng = random.Random(cfg.seed)
        seeds.append(tour)
        for _ in range(cfg.seed_copies - 1):
            copy = tour[:]
            mutate(copy, rng)
            seeds.append(copy)

    remaining = cfg.time_limit_s - (time.perf_counter() - start)
    if remaining < MIN_GA_SECONDS:
        diag = {"ortools_phase": ort_diag, "ga_phase": None, "seeded": bool(seeds),
                "note": "no time left for the GA phase; plan is the OR-Tools phase result"}
        status = R.SOLVED if ort.routes is not None else ort.status
        return result(status, time.perf_counter() - start, ort.routes, diag=diag)

    ga_cfg = GAConfig(**{**cfg.ga, "time_limit_s": remaining, "local_search": cfg.local_search,
                         "seed": cfg.seed, "max_generations": 10**9, "stagnation_generations": None})
    ga = solve_ga(instance, ga_cfg, initial_tours=seeds)
    diag = {"ortools_phase": ort_diag, "ga_phase": ga.diagnostics, "seeded": bool(seeds),
            "ga_seconds": ga.runtime_seconds}
    if ga.routes is None:  # GA failed: say so; fall back to the OR-Tools plan only if there is one
        msg = f"GA phase failed ({ga.status}: {ga.message})"
        if ort.routes is not None:
            return result(R.SOLVED, time.perf_counter() - start, ort.routes,
                          message=msg + "; plan is the OR-Tools phase result", diag=diag)
        return result(ga.status, time.perf_counter() - start, message=msg, diag=diag)
    final = _distance(instance, ga.routes)
    seed_d = ort_diag["seed_distance"]
    diag["improved_over_seed"] = (final is not None and seed_d is not None and final < seed_d - 1e-9)
    msg = "" if seeds else "OR-Tools phase found no plan; GA ran unseeded"
    return result(R.SOLVED, time.perf_counter() - start, ga.routes, message=msg, diag=diag)
