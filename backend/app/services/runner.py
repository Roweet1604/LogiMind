"""Run one solver on one instance and attach shared validation + metrics."""
from __future__ import annotations

import math
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from app.evaluation.metrics import Metrics, compute_metrics
from app.evaluation.validator import ValidationResult, validate_routes
from app.models import result as R
from app.models.problem import Instance
from app.solvers.genetic_algorithm import GAConfig, solve_ga
from app.solvers.hybrid import HybridConfig, solve_hybrid
from app.solvers.ortools_solver import solve_ortools

ALGORITHMS = ("ortools", "ga", "hybrid")


def environment_info() -> dict[str, Any]:
    def ver(pkg: str) -> str:
        try:
            return metadata.version(pkg)
        except metadata.PackageNotFoundError:
            return "not installed"
    import os
    return {
        "python": sys.version.split()[0], "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(), "cpu_count": os.cpu_count(),
        "ortools": ver("ortools"), "numpy": ver("numpy"), "pandas": ver("pandas"),
    }


@dataclass
class RunRecord:
    instance: Instance
    result: R.SolveResult
    validation: ValidationResult | None
    metrics: Metrics | None
    started_at: str

    def to_row(self) -> dict[str, Any]:
        """Flat row for CSV. Missing metrics stay NaN/blank, never 0."""
        nan = math.nan
        m, v, r = self.metrics, self.validation, self.result
        return {
            "run_id": r.run_id, "instance_id": r.instance_id, "instance_name": self.instance.name,
            "n_customers": len(self.instance.customers), "algorithm": r.algorithm, "seed": r.seed,
            "status": r.status, "feasible": (v.feasible if v else None),
            "runtime_seconds": r.runtime_seconds,
            "total_distance": m.total_distance if m else nan,
            "estimated_cost": m.estimated_cost if m else nan,
            "vehicles_used": m.vehicles_used if m else nan,
            "unserved_customers": m.unserved_customers if m else nan,
            "capacity_violations": m.capacity_violations if m else nan,
            "other_violations": m.other_violations if m else nan,
            "time_window_violations": m.time_window_violations if m else nan,
            "total_lateness": m.total_lateness if m else nan,
            "has_time_windows": self.instance.has_time_windows,
            "distance_unit": self.instance.distance_unit, "metric": self.instance.metric,
            "vehicle_count": self.instance.vehicle_count, "vehicle_capacity": self.instance.vehicle_capacity,
            "fixed_vehicle_cost": self.instance.fixed_vehicle_cost,
            "cost_per_distance": self.instance.cost_per_distance,
            "config": str(r.config), "message": r.message, "started_at": self.started_at,
        }


def run_algorithm(instance: Instance, algorithm: str, config: dict[str, Any] | None = None) -> RunRecord:
    """Dispatch to a solver, then validate and score the routes with the shared code."""
    config = dict(config or {})
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if algorithm == "ortools":
        res = solve_ortools(instance, **config)
    elif algorithm == "ga":
        initial_tours = config.pop("initial_tours", None)  # P7 warm start; not a GAConfig field
        try:
            res = solve_ga(instance, GAConfig(**config), initial_tours=initial_tours)
            if initial_tours is not None:
                res.config = {**res.config, "initial_tours": len(initial_tours)}
        except TypeError as exc:  # unknown GA setting
            res = R.SolveResult(instance.instance_id, "ga", R.INVALID_INPUT, 0.0, None, config,
                                seed=config.get("seed"), message=f"invalid GA config: {exc}")
    elif algorithm == "hybrid":
        try:
            res = solve_hybrid(instance, HybridConfig(**config))
        except TypeError as exc:  # unknown hybrid setting
            res = R.SolveResult(instance.instance_id, "hybrid", R.INVALID_INPUT, 0.0, None, config,
                                seed=config.get("seed"), message=f"invalid hybrid config: {exc}")
    else:
        raise ValueError(f"unknown algorithm {algorithm!r}; expected one of {ALGORITHMS}")

    validation = metrics = None
    if res.routes is not None:
        validation = validate_routes(instance, res.routes)
        metrics = compute_metrics(instance, res.routes, validation)
    return RunRecord(instance, res, validation, metrics, started)
