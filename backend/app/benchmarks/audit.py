"""OR-Tools configuration audit (P2): first-solution strategy x metaheuristic x
time budget x repeats, on benchmark and synthetic instances.

OR-Tools' routing search has no random-seed parameter, so a "repeat" is the
same configuration run again. Differences between repeats come from the
wall-clock limit (how much search fits in the budget on a busy machine), not
from a seed. GREEDY_DESCENT stops at its first local optimum and usually ends
before the budget; the other metaheuristics always use the whole budget.

Every row records the configuration, the repeat index, the budget, the
OR-Tools status and the software versions, so each run can be traced.
Gaps are reported two ways:
- gap_to_bks_pct: against the published best-known value (benchmarks only);
- gap_to_best_observed_pct: against the best feasible distance found anywhere
  in this audit for that instance. This is NOT a best-known value; it only
  exists so synthetic instances (which have no BKS) can be ranked too.
"""
from __future__ import annotations

import csv
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from app.benchmarks.catalog import gap_pct, load_bks, load_instance
from app.models.problem import Instance
from app.services.generator import generate_instance
from app.services.runner import environment_info, run_algorithm
from app.solvers.ortools_solver import budget_class

FIRST_SOLUTIONS = ["PATH_CHEAPEST_ARC", "SAVINGS", "PARALLEL_CHEAPEST_INSERTION", "LOCAL_CHEAPEST_INSERTION"]
METAHEURISTICS = ["GREEDY_DESCENT", "GUIDED_LOCAL_SEARCH", "SIMULATED_ANNEALING", "TABU_SEARCH"]
BUDGETS = [1.0, 3.0, 10.0]
REPEATS = 3
INSTANCES = [
    "solomon:C101", "solomon:C201", "solomon:R101", "solomon:R201", "solomon:RC101", "solomon:RC201",
    "A:A-n32-k5", "A:A-n60-k9", "A:A-n80-k10", "X:X-n101-k25",
    "synthetic:50", "synthetic:100",
]
# Metaheuristics that never stop on their own: they always spend the full budget.
TIME_BOUND_METAHEURISTICS = {"GUIDED_LOCAL_SEARCH", "SIMULATED_ANNEALING", "TABU_SEARCH"}


def load_audit_instance(key: str) -> tuple[Instance, str]:
    """`set:name` for a downloaded benchmark, `synthetic:<n>` for a generated
    CVRP (seed = n, haversine; labelled synthetic). Returns (instance, problem class)."""
    set_key, _, name = key.partition(":")
    if set_key == "synthetic":
        inst = generate_instance(int(name), seed=int(name), metric="haversine")
    else:
        inst = load_instance(set_key, name)
    return inst, ("VRPTW" if inst.has_time_windows else "CVRP")


@dataclass(frozen=True)
class Job:
    instance_key: str
    first_solution: str
    metaheuristic: str
    budget_s: float
    repeat: int


def plan_jobs(instances: list[str], first_solutions: list[str], metaheuristics: list[str],
              budgets: list[float], repeats: int) -> list[Job]:
    """Repeats are the outer loop, so slow drift in machine load spreads over
    all configurations instead of hitting one of them."""
    return [Job(i, fs, mh, b, r) for r in range(repeats) for i in instances
            for fs in first_solutions for mh in metaheuristics for b in budgets]


def estimate_seconds(jobs: list[Job], greedy_s: float = 1.0) -> float:
    """Upper-bound-style estimate: time-bound metaheuristics use the full budget;
    GREEDY_DESCENT is charged `greedy_s` (it can use the full budget when the
    first-solution step fails, which is why this is an estimate)."""
    return sum(j.budget_s if j.metaheuristic in TIME_BOUND_METAHEURISTICS else min(greedy_s, j.budget_s)
               for j in jobs)


def git_commit(repo: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True,
                              text=True, timeout=10).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_job(job: Job, inst: Instance, problem: str, env: dict[str, Any], commit: str,
            bks: dict) -> dict[str, Any]:
    rec = run_algorithm(inst, "ortools", {"time_limit_s": job.budget_s, "first_solution": job.first_solution,
                                          "metaheuristic": job.metaheuristic})
    row = rec.to_row()
    diag = rec.result.diagnostics
    name = job.instance_key.partition(":")[2]
    b = bks.get(name) if not job.instance_key.startswith("synthetic:") else None
    feasible = row["feasible"] is True
    row.update({
        "instance_key": job.instance_key, "problem": problem, "first_solution": job.first_solution,
        "metaheuristic": job.metaheuristic, "budget_s": job.budget_s, "budget_class": budget_class(job.budget_s),
        "repeat": job.repeat, "seed_note": "OR-Tools routing has no seed; repeat = same config run again",
        "ortools_status": diag.get("ortools_status", ""), "build_seconds": diag.get("build_seconds", math.nan),
        "search_limit_s": diag.get("search_limit_s", math.nan),
        "bks_cost": b.cost if b else math.nan, "bks_source": b.source_url if b else "",
        "gap_to_bks_pct": gap_pct(row["total_distance"], b.cost) if (b and feasible) else math.nan,
        "python": env["python"], "ortools_version": env["ortools"], "numpy_version": env["numpy"],
        "platform": env["platform"], "processor": env["processor"], "cpu_count": env["cpu_count"],
        "git_commit": commit,
    })
    return row


def iter_runs(jobs: list[Job], repo: Path, done: set[tuple] | None = None) -> Iterator[dict[str, Any]]:
    """Run the jobs one at a time (never in parallel: timing must not be shared)."""
    env, commit, bks = environment_info(), git_commit(repo), load_bks()
    cache: dict[str, tuple[Instance, str]] = {}
    for job in jobs:
        if done and job_key(job) in done:
            continue
        if job.instance_key not in cache:
            cache[job.instance_key] = load_audit_instance(job.instance_key)
        inst, problem = cache[job.instance_key]
        yield run_job(job, inst, problem, env, commit, bks)


def job_key(job: Job) -> tuple:
    return (job.instance_key, job.first_solution, job.metaheuristic, float(job.budget_s), int(job.repeat))


def done_keys(raw_csv: Path) -> set[tuple]:
    if not raw_csv.exists():
        return set()
    with raw_csv.open(newline="", encoding="utf-8") as f:
        return {(r["instance_key"], r["first_solution"], r["metaheuristic"], float(r["budget_s"]), int(r["repeat"]))
                for r in csv.DictReader(f)}


# ---------------------------------------------------------------- analysis

CONFIG = ["first_solution", "metaheuristic"]
# A run whose wall clock exceeds its budget by this factor did not get a normal,
# comparable budget (e.g. the machine froze or slept). It stays in raw.csv but is
# left out of every statistic and listed in the report instead.
ANOMALY_FACTOR = 1.5


def timing_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["runtime_seconds"].astype(float) > ANOMALY_FACTOR * df["budget_s"].astype(float)]


def add_best_observed(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(index=timing_anomalies(df).index)
    feas = df["feasible"].astype(str) == "True"
    best = df[feas].groupby("instance_key")["total_distance"].min()
    df["feasible_bool"] = feas
    df["best_observed"] = df["instance_key"].map(best)
    df["gap_to_best_observed_pct"] = [
        100.0 * (d - b) / b if (f and b and b > 0) else math.nan
        for d, b, f in zip(df["total_distance"], df["best_observed"], feas)]
    return df


def summarize_configs(df: pd.DataFrame) -> pd.DataFrame:
    """Per (problem, budget, config): success counts and gap statistics.
    Gap means are over feasible runs only; failures are counted, never averaged in."""
    df = add_best_observed(df)
    rows = []
    for (problem, budget, fs, mh), g in df.groupby(["problem", "budget_s"] + CONFIG):
        ok = g[g["feasible_bool"]]
        rows.append({
            "problem": problem, "budget_s": budget, "budget_class": budget_class(budget),
            "first_solution": fs, "metaheuristic": mh, "runs": len(g), "feasible_runs": len(ok),
            "instances": g["instance_key"].nunique(),
            "instances_always_solved": int((g.groupby("instance_key")["feasible_bool"].all()).sum()),
            "mean_gap_best_observed_pct": ok["gap_to_best_observed_pct"].mean() if len(ok) else math.nan,
            "mean_gap_bks_pct": ok["gap_to_bks_pct"].astype(float).mean() if len(ok) else math.nan,
            "mean_runtime_s": g["runtime_seconds"].astype(float).mean(),
        })
    return pd.DataFrame(rows).sort_values(["problem", "budget_s", "mean_gap_best_observed_pct"])


def repeat_variation(df: pd.DataFrame) -> pd.DataFrame:
    """Run-to-run variation: for each (instance, config, budget) with >= 2 feasible
    repeats, the spread (max - min) of the distance as % of the best repeat."""
    df = add_best_observed(df)
    rows = []
    for (key, problem, budget, fs, mh), g in df.groupby(["instance_key", "problem", "budget_s"] + CONFIG):
        d = g[g["feasible_bool"]]["total_distance"].astype(float)
        rows.append({"instance_key": key, "problem": problem, "budget_s": budget, "first_solution": fs,
                     "metaheuristic": mh, "repeats": len(g), "feasible_repeats": len(d),
                     "spread_pct": 100.0 * (d.max() - d.min()) / d.min() if len(d) >= 2 else math.nan,
                     "std_distance": d.std(ddof=1) if len(d) >= 2 else math.nan})
    return pd.DataFrame(rows)


def recommend(summary: pd.DataFrame) -> pd.DataFrame:
    """Per (problem, budget): the configuration that solved every instance in
    every repeat, with the lowest mean gap to the best observed distance.
    If no configuration solved everything, the row says so (no fake winner)."""
    rows = []
    for (problem, budget), g in summary.groupby(["problem", "budget_s"]):
        full = g[g["feasible_runs"] == g["runs"]].sort_values("mean_gap_best_observed_pct")
        if full.empty:
            rows.append({"problem": problem, "budget_s": budget, "budget_class": budget_class(budget),
                         "first_solution": "", "metaheuristic": "", "note": "no configuration solved all runs"})
            continue
        top = full.iloc[0]
        rows.append({"problem": problem, "budget_s": budget, "budget_class": budget_class(budget),
                     "first_solution": top["first_solution"], "metaheuristic": top["metaheuristic"],
                     "mean_gap_best_observed_pct": top["mean_gap_best_observed_pct"],
                     "mean_gap_bks_pct": top["mean_gap_bks_pct"], "note": ""})
    return pd.DataFrame(rows)
