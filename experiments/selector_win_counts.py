"""P5 step 1: count engine wins in the existing P3 equal-clock comparison.

Reads experiments/results/compare_2026-11-02/raw.csv (no solver runs). A *case* is one
instance x one budget; each engine's score is its mean total distance over its seeds,
counted only when every run of that engine on the case was feasible. The winner is the
lowest mean distance; engines within 0.01% of the best count as tied.

Engines compared (as asked for P5): ortools, ga_ls (GA + fleet repair + local search),
hybrid (= hybrid_seed_ls, the hybrid's default variant). The OR-Tools audit has only
OR-Tools runs, so it cannot count engine wins; it is used for the OR-Tools-settings view.

Usage: python experiments/selector_win_counts.py [--out experiments/results/selector_2026-11-04]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
COMPARE = ROOT / "results" / "compare_2026-11-02" / "raw.csv"
AUDIT = ROOT / "results" / "ortools_audit_2026-11-02" / "raw.csv"
ENGINES = {"ortools": "ortools", "ga_ls": "ga_ls", "hybrid_seed_ls": "hybrid"}
TIE_REL = 1e-4


def family(key: str) -> str:
    if key.startswith("solomon:"):
        name = key.split(":")[1]  # e.g. RC201 -> solomon_RC2
        letters = name.rstrip("0123456789")
        return f"solomon_{letters}{name[len(letters)]}"
    return key.split(":")[0]


def case_winners(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[raw["method"].isin(ENGINES)].copy()
    df["engine"] = df["method"].map(ENGINES)
    rows = []
    for (key, budget), g in df.groupby(["instance_key", "budget_s"]):
        scores = {}
        for eng, ge in g.groupby("engine"):
            if bool(ge["feasible"].astype(str).eq("True").all()):
                scores[eng] = float(ge["total_distance"].mean())
        if not scores:
            continue
        best = min(scores.values())
        tied = sorted(e for e, s in scores.items() if s <= best * (1 + TIE_REL))
        rows.append({"instance_key": key, "family": family(key), "problem": g["problem"].iloc[0],
                     "n_customers": int(g["n_customers"].iloc[0]), "budget_s": budget,
                     "winners": "+".join(tied), "sole_winner": tied[0] if len(tied) == 1 else "tie",
                     **{f"dist_{e}": scores.get(e) for e in ENGINES.values()}})
    return pd.DataFrame(rows)


def shares(cases: pd.DataFrame) -> dict:
    n = len(cases)
    out = {"cases": n}
    for e in ENGINES.values():
        wins_or_ties = int(cases["winners"].str.split("+").apply(lambda w: e in w).sum())
        sole = int((cases["sole_winner"] == e).sum())
        out[e] = {"wins_or_ties": wins_or_ties, "share_wins_or_ties": wins_or_ties / n if n else 0.0,
                  "sole_wins": sole, "share_sole_wins": sole / n if n else 0.0}
    out["ties"] = int((cases["sole_winner"] == "tie").sum())
    return out


def audit_settings_view(audit: pd.DataFrame) -> pd.DataFrame:
    """Per instance x budget: the best OR-Tools setting and whether the old default failed."""
    a = audit[audit["runtime_seconds"] < 100].copy()  # the one 1506 s anomaly is excluded (see P2 report)
    a["ok"] = a["feasible"].astype(str).eq("True")
    a["setting"] = a["first_solution"] + "+" + a["metaheuristic"]
    rows = []
    for (key, budget), g in a.groupby(["instance_key", "budget_s"]):
        mean = g[g["ok"]].groupby("setting")["total_distance"].mean()
        default = g[g["setting"] == "PATH_CHEAPEST_ARC+GUIDED_LOCAL_SEARCH"]
        rows.append({"instance_key": key, "problem": g["problem"].iloc[0], "budget_s": budget,
                     "best_setting": mean.idxmin() if len(mean) else None,
                     "n_settings_failing": int((~g.groupby("setting")["ok"].all()).sum()),
                     "pca_gls_failed": bool(len(default)) and not bool(default["ok"].all())})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "selector_2026-11-04"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = case_winners(pd.read_csv(COMPARE))
    cases.to_csv(out / "engine_wins_cases.csv", index=False)
    summary = {"overall": shares(cases)}
    for col in ("problem", "family", "budget_s", "n_customers"):
        summary[f"by_{col}"] = {str(k): shares(g) for k, g in cases.groupby(col)}
    (out / "engine_wins_summary.json").write_text(json.dumps(summary, indent=2))
    if AUDIT.exists():
        audit_settings_view(pd.read_csv(AUDIT)).to_csv(out / "ortools_best_setting_by_case.csv", index=False)
    print(cases.to_string(index=False))
    print(json.dumps(summary["overall"], indent=2))
    for col in ("problem", "budget_s"):
        for k, s in summary[f"by_{col}"].items():
            print(col, k, {e: (s[e]["wins_or_ties"], s[e]["sole_wins"]) for e in ENGINES.values()}, "cases", s["cases"])


if __name__ == "__main__":
    main()
