"""Out-of-distribution test of the engine picker (selector) on the held-out BENCHMARK runs (no solver runs here).

The selector was trained on synthetic instances (20-80 customers, budgets 1 and 3 s). Here it chooses an engine for
each held-out benchmark case (24 instances x 3 s and 10 s), and its choice is scored against what the three engines
actually achieved in the stored runs:

  case            = (instance, budget)
  engine distance = mean total distance over that engine's FEASIBLE repeats (3 repeats; training had 1 run)
  regret          = % extra distance of the chosen engine over the best engine of the case (training definition);
                    a choice with no feasible repeat counts as a failed choice and is left out of the regret means
  baselines       = always OR-Tools, always GA + LS, always hybrid, random (expected value), oracle

Inputs: experiments/results/heldout_2026-11-05/raw.csv (3 s), experiments/results/heldout_10s_2026-11-05/raw.csv (10 s)
Output: experiments/results/selector_heldout_2026-11-05/ (cases.csv, summary.csv, manifest.json)
Usage (repo root): python experiments/selector_heldout_eval.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.benchmarks.catalog import load_instance  # noqa: E402
from app.selector.dataset import ENGINES  # noqa: E402
from app.selector.model import get_selector  # noqa: E402

RES = ROOT / "experiments" / "results"
RUNS = [RES / "heldout_2026-11-05" / "raw.csv", RES / "heldout_10s_2026-11-05" / "raw.csv"]
OUT = RES / "selector_heldout_2026-11-05"
METHOD_OF = {"ortools": "ortools", "hybrid": "hybrid_seed_ls", "ga_ls": "ga_ls"}  # selector engine -> run method
TIE = 0.01  # % : a choice within this of the best counts as correct


def cases_from(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (key, budget), g in raw.groupby(["instance_key", "budget_s"], sort=True):
        row = {"instance_key": key, "instance_name": g["instance_name"].iloc[0], "problem": g["problem"].iloc[0],
               "n_customers": int(g["n_customers"].iloc[0]), "budget_s": float(budget)}
        for e in ENGINES:
            runs = g[g["method"] == METHOD_OF[e]]
            ok = runs[runs["feasible"] == True]  # noqa: E712
            row[f"dist_{e}"] = float(ok["total_distance"].mean()) if len(ok) else math.nan
            row[f"feasible_{e}"] = f"{len(ok)}/{len(runs)}"
        rows.append(row)
    return pd.DataFrame(rows)


def regret(case: pd.Series, engine: str) -> float:
    d, best = case[f"dist_{engine}"], case["best_dist"]
    if math.isnan(d):
        return math.inf
    return 100.0 * (d - best) / best


def score(cases: pd.DataFrame, chosen: list[str]) -> dict:
    r = [regret(c, e) for (_, c), e in zip(cases.iterrows(), chosen)]
    finite = [x for x in r if math.isfinite(x)]
    return {"cases": len(r), "correct": int(sum(x <= TIE for x in finite)), "failures": len(r) - len(finite),
            "mean_regret_pct": float(np.mean(finite)) if finite else math.nan,
            "median_regret_pct": float(np.median(finite)) if finite else math.nan,
            "max_regret_pct": float(np.max(finite)) if finite else math.nan}


def main() -> None:
    raw = pd.concat([pd.read_csv(p) for p in RUNS], ignore_index=True)
    # timing anomalies (longer than the guard's hard limit, 1.5 x budget + 5 s) are left out, as in p10_report.py
    slow = raw["runtime_seconds"] > 1.5 * raw["budget_s"] + 5.0
    excluded = raw[slow][["instance_name", "method", "seed", "budget_s", "runtime_seconds"]].to_dict("records")
    raw = raw[~slow]
    cases = cases_from(raw)
    cases["best_dist"] = cases[[f"dist_{e}" for e in ENGINES]].min(axis=1)
    sel = get_selector()
    if sel.model is None:
        raise SystemExit("no trained selector available")
    picks, outside = [], []
    for c in cases.itertuples():
        set_key, name = c.instance_key.split(":", 1)
        s = sel.choose(load_instance(set_key, name), c.budget_s)
        picks.append(s.engine)
        outside.append("; ".join(s.details.get("outside_training_range", [])))
    cases["selector_choice"] = picks
    cases["outside_training_range"] = outside
    cases["best_engine"] = [min(ENGINES, key=lambda e, c=c: c[f"dist_{e}"] if not math.isnan(c[f"dist_{e}"])
                                else math.inf) for _, c in cases.iterrows()]
    for e in ENGINES:
        cases[f"regret_{e}"] = [regret(c, e) for _, c in cases.iterrows()]

    rows = []
    for scope, sub in [("all", cases)] + [(f"{p}", g) for p, g in cases.groupby("problem")] + \
            [(f"{b:g} s", g) for b, g in cases.groupby("budget_s")]:
        strategies = {"selector (served regret model)": list(sub["selector_choice"]),
                      **{f"always {e}": [e] * len(sub) for e in ENGINES},
                      "oracle": list(sub["best_engine"])}
        for name, chosen in strategies.items():
            rows.append({"scope": scope, "strategy": name, **score(sub, chosen)})
        rand = [score(sub, [e] * len(sub)) for e in ENGINES]  # expected value of a uniform random pick
        finite = [x["mean_regret_pct"] for x in rand if math.isfinite(x["mean_regret_pct"])]
        rows.append({"scope": scope, "strategy": "random (expected)", "cases": len(sub),
                     "correct": float(np.mean([x["correct"] for x in rand])),
                     "failures": float(np.mean([x["failures"] for x in rand])),
                     "mean_regret_pct": float(np.mean(finite)) if finite else math.nan,
                     "median_regret_pct": math.nan, "max_regret_pct": math.nan})
    summary = pd.DataFrame(rows)

    OUT.mkdir(parents=True, exist_ok=True)
    cases.to_csv(OUT / "cases.csv", index=False)
    summary.to_csv(OUT / "summary.csv", index=False)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout
    (OUT / "manifest.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_commit": commit.strip(),
        "inputs": [str(p.relative_to(ROOT)) for p in RUNS], "selector_training_cases": int(len(sel.cases)),
        "selector_training_sizes": [int(sel.cases["n_customers"].min()), int(sel.cases["n_customers"].max())],
        "selector_training_budgets": sorted(float(b) for b in sel.cases["budget_s"].unique()),
        "cases": int(len(cases)), "cases_outside_training_range": int((cases["outside_training_range"] != "").sum()),
        "runs_used": {str(p.relative_to(ROOT)): int(len(pd.read_csv(p))) for p in RUNS},
        "excluded_timing_anomalies": excluded,
        "partial_10s": bool(len(pd.read_csv(RUNS[1])) < json.loads((RUNS[1].parent / "manifest.json").read_text())
                            ["planned_runs"]),
        "regret_definition": "% extra distance over the best engine's mean feasible distance on the case; "
                             "failed choice = chosen engine had no feasible repeat", "tie_pct": TIE,
        "note": "No solver runs: choices are scored against the stored held-out benchmark runs."}, indent=1))
    print(summary[summary["scope"] == "all"].to_string(index=False))


if __name__ == "__main__":
    main()
