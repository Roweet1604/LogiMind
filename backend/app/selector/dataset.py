"""Selector dataset: case grid, engine configurations and labelling.

A case is one synthetic instance x one time budget. Each engine runs once per case
with the same total budget. The label is the engine with the lowest total distance
among the feasible runs; ties (within 0.01%) go to the earlier engine in ENGINES
(OR-Tools first, the simplest and most stable choice).
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.selector.generator import FAMILIES

GA_TIME_ONLY = {"max_generations": 10**9, "stagnation_generations": None}
# engine -> (algorithm, config without budget/seed); same settings as the P3 comparison.
ENGINE_CONFIGS: dict[str, tuple[str, dict[str, Any]]] = {
    "ortools": ("ortools", {}),
    "hybrid": ("hybrid", {"local_search": True}),
    "ga_ls": ("ga", {**GA_TIME_ONLY, "local_search": True}),
}
ENGINES = tuple(ENGINE_CONFIGS)
TIE_REL = 1e-4


def plan_cases(sizes: list[int], tightness: list[str], budgets: list[float], seeds: int) -> list[dict[str, Any]]:
    cases = []
    for seed in range(seeds):
        for family in FAMILIES:
            for n in sizes:
                for tight in tightness:
                    ikey = f"{family}-n{n}-{tight}-s{seed}"
                    for b in budgets:
                        cases.append({"case_id": f"{ikey}-b{b:g}", "instance_key": ikey, "family": family,
                                      "n_customers": n, "tightness": tight, "seed": seed, "budget_s": b})
    return cases


def label_cases(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per case: features, per-engine distance (NaN = infeasible/no plan), label."""
    raw = raw.copy()
    raw["ok"] = raw["feasible"].astype(str).eq("True")
    fcols = [c for c in raw.columns if c.startswith("f_")]
    rows = []
    for case_id, g in raw.groupby("case_id", sort=False):
        dist = {e: math.nan for e in ENGINES}
        for _, r in g.iterrows():
            if r["ok"]:
                dist[r["engine"]] = float(r["total_distance"])
        feasible = {e: d for e, d in dist.items() if not math.isnan(d)}
        first = g.iloc[0]
        row = {"case_id": case_id, "family": first["family"], "n_customers": int(first["n_customers"]),
               "tightness": first["tightness"], "budget_s": float(first["budget_s"]),
               **{c: float(first[c]) for c in fcols}, **{f"dist_{e}": dist[e] for e in ENGINES}}
        if feasible:
            best = min(feasible.values())
            row["best_dist"] = best
            row["label"] = next(e for e in ENGINES if e in feasible and feasible[e] <= best * (1 + TIE_REL))
        else:
            row["best_dist"], row["label"] = math.nan, "none_feasible"
        rows.append(row)
    return pd.DataFrame(rows)


def regret_pct(case: pd.Series, engine: str) -> float:
    """% extra distance of `engine` over the best engine on this case; inf if it had no feasible plan."""
    d = case[f"dist_{engine}"]
    if math.isnan(case["best_dist"]):
        return 0.0
    if math.isnan(d):
        return math.inf
    return 100.0 * (d - case["best_dist"]) / case["best_dist"]
