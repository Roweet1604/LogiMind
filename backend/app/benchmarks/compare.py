"""P3 engine comparison and ablation under the equal-clock rule.

Every method gets the SAME total wall-clock budget on the same instance object
(same distance matrix, same objective). The hybrid's OR-Tools phase is part of
its budget. Runs go one at a time through the wall-clock guard, so a run that
hangs is recorded as `hard_timeout` instead of stalling the experiment.

GA-based methods use seeds 0..k-1; OR-Tools has no seed, so its "seed" column
is a repeat index (see the P2 audit).
"""
from __future__ import annotations

import math
from typing import Any, Iterator

import pandas as pd

from app.benchmarks.audit import add_best_observed, git_commit, load_audit_instance
from app.benchmarks.catalog import gap_pct, load_bks
from app.services.guard import GuardedWorker
from app.services.runner import environment_info

GA_TIME_ONLY = {"max_generations": 10**9, "stagnation_generations": None}
# method -> (algorithm, config without budget/seed). Order = table order.
METHODS: dict[str, tuple[str, dict[str, Any]]] = {
    "ortools": ("ortools", {}),
    "ga_nofix": ("ga", {**GA_TIME_ONLY, "fleet_repair": False}),
    "ga": ("ga", dict(GA_TIME_ONLY)),
    "ga_ls": ("ga", {**GA_TIME_ONLY, "local_search": True}),
    "hybrid_seed": ("hybrid", {"local_search": False}),
    "hybrid_seed_ls": ("hybrid", {"local_search": True}),
}
LABELS = {
    "ortools": "OR-Tools (audited defaults)",
    "ga_nofix": "GA, P1 version (no fleet repair)",
    "ga": "GA + fleet repair",
    "ga_ls": "GA + fleet repair + local search",
    "hybrid_seed": "Hybrid: OR-Tools seed, no local search",
    "hybrid_seed_ls": "Hybrid: OR-Tools seed + local search",
}
INSTANCES = ["solomon:C101", "solomon:R101", "solomon:RC101", "solomon:R201", "solomon:RC201",
             "A:A-n32-k5", "A:A-n80-k10", "X:X-n101-k25", "synthetic:50", "synthetic:100"]
BUDGETS = [3.0, 10.0]
SEEDS = 3


def plan_jobs(instances: list[str], methods: list[str], budgets: list[float], seeds: int) -> list[tuple]:
    """(instance, method, budget, seed); seeds outermost so machine drift spreads over methods."""
    return [(i, m, b, s) for s in range(seeds) for i in instances for b in budgets for m in methods]


def job_config(method: str, budget: float, seed: int) -> tuple[str, dict[str, Any]]:
    algorithm, base = METHODS[method]
    cfg = {**base, "time_limit_s": budget}
    if algorithm != "ortools":
        cfg["seed"] = seed
    return algorithm, cfg


def estimate_seconds(jobs: list[tuple]) -> float:
    return sum(b for _, _, b, _ in jobs)


def iter_runs(jobs: list[tuple], repo, done: set[tuple] | None = None,
              worker: GuardedWorker | None = None) -> Iterator[dict[str, Any]]:
    env, commit, bks = environment_info(), git_commit(repo), load_bks()
    worker = worker or GuardedWorker()
    cache: dict[str, tuple] = {}
    try:
        for key, method, budget, seed in jobs:
            if done and (key, method, float(budget), int(seed)) in done:
                continue
            if key not in cache:
                cache[key] = load_audit_instance(key)
            inst, problem = cache[key]
            algorithm, cfg = job_config(method, budget, seed)
            rec = worker.run(inst, algorithm, cfg)
            row = rec.to_row()
            name = key.partition(":")[2]
            b = None if key.startswith("synthetic:") else bks.get(name)
            feasible = row["feasible"] is True
            diag = rec.result.diagnostics
            row.update({
                "instance_key": key, "problem": problem, "method": method, "budget_s": budget, "seed": seed,
                "routes_used": sum(1 for r in (rec.result.routes or []) if r) if rec.result.routes else math.nan,
                "bks_cost": b.cost if b else math.nan,
                "gap_to_bks_pct": gap_pct(row["total_distance"], b.cost) if (b and feasible) else math.nan,
                "hybrid_seeded": diag.get("seeded", ""),
                "hybrid_seed_distance": (diag.get("ortools_phase") or {}).get("seed_distance", math.nan),
                "hybrid_improved_over_seed": diag.get("improved_over_seed", ""),
                "python": env["python"], "ortools_version": env["ortools"], "numpy_version": env["numpy"],
                "platform": env["platform"], "processor": env["processor"], "git_commit": commit,
            })
            yield row
    finally:
        worker.close()


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Per (problem, budget, method). Gap means over feasible runs only; failures counted."""
    timeouts = df[df["status"] == "hard_timeout"].groupby(["problem", "budget_s", "method"]).size()
    df = add_best_observed(df)  # drops timing anomalies (incl. guard timeouts); counted separately
    rows = []
    for (problem, budget, method), g in df.groupby(["problem", "budget_s", "method"]):
        ok = g[g["feasible_bool"]]
        rows.append({
            "problem": problem, "budget_s": budget, "method": method, "runs": len(g), "feasible_runs": len(ok),
            "hard_timeouts": int(timeouts.get((problem, budget, method), 0)),
            "mean_gap_bks_pct": ok["gap_to_bks_pct"].astype(float).mean() if len(ok) else math.nan,
            "mean_gap_best_observed_pct": ok["gap_to_best_observed_pct"].mean() if len(ok) else math.nan,
            "mean_runtime_s": g["runtime_seconds"].astype(float).mean(),
            "max_runtime_s": g["runtime_seconds"].astype(float).max(),
        })
    out = pd.DataFrame(rows)
    order = {m: i for i, m in enumerate(METHODS)}
    return out.sort_values(["problem", "budget_s", "method"], key=lambda c: c.map(order) if c.name == "method" else c)


def per_instance(df: pd.DataFrame) -> pd.DataFrame:
    """Feasible runs / runs and mean routes per (instance, budget, method)."""
    df = add_best_observed(df)
    g = df.groupby(["instance_key", "budget_s", "method"])
    return pd.DataFrame({
        "runs": g.size(), "feasible_runs": g["feasible_bool"].sum(),
        "mean_routes": g["routes_used"].mean(), "vehicle_limit": g["vehicle_count"].first(),
        "mean_gap_bks_pct": g["gap_to_bks_pct"].mean(),
    }).reset_index()
