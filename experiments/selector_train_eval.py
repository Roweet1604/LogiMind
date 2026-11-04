"""P5: label the selector dataset, run grouped CV and baselines, write the report.

Reads <out>/dataset_raw.csv (from selector_dataset.py), writes <out>/cases.csv,
<out>/evaluation.json, <out>/evaluation.md, and copies cases.csv to
backend/app/selector/data/training_cases.csv (the selector's training data).
No solver runs here. All data is synthetic.

Usage: python experiments/selector_train_eval.py [--out experiments/results/selector_2026-11-04]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.selector.dataset import ENGINES, label_cases  # noqa: E402
from app.selector.features import FEATURE_NAMES  # noqa: E402
from app.selector.model import DATA_PATH, evaluate, fit  # noqa: E402

ROWS = ["selector", "selector_regret_model", *[f"always_{e}" for e in ENGINES], "random", "oracle"]


def table(ev: dict) -> str:
    lines = ["| Strategy | Accuracy | Mean regret % | Max regret % | Failed choices |",
             "| --- | --- | --- | --- | --- |"]
    for k in ROWS:
        s = ev[k]
        mx = s.get("max_regret_pct", float("nan"))
        lines.append(f"| {k} | {s['accuracy']:.3f} | {s['mean_regret_pct']:.2f} | "
                     f"{'-' if k == 'random' else f'{mx:.2f}'} | {s['failures']:g} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "experiments" / "results" / "selector_2026-11-04"))
    args = ap.parse_args()
    out = Path(args.out)
    raw = pd.read_csv(out / "dataset_raw.csv")
    cases = label_cases(raw)
    cases.to_csv(out / "cases.csv", index=False)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / "cases.csv", DATA_PATH)

    ev_family = evaluate(cases, "family")
    ev_size = evaluate(cases, "n_customers")
    model = fit(cases)
    importances = dict(sorted(zip(FEATURE_NAMES, map(float, model.feature_importances_)),
                              key=lambda kv: -kv[1]))
    status = raw.groupby(["engine", "status"]).size().unstack(fill_value=0).to_dict(orient="index")
    feas = raw.assign(ok=raw["feasible"].astype(str).eq("True")).groupby("engine")["ok"].agg(["sum", "count"])
    report = {"data": "synthetic", "runs": int(len(raw)), "cases": int(len(cases)),
              "status_by_engine": status, "feasible_by_engine": feas.to_dict(orient="index"),
              "label_counts": cases["label"].value_counts().to_dict(),
              "label_by_tightness_budget": {f"{t} {b:g}s": g["label"].value_counts().to_dict()
                                            for (t, b), g in cases.groupby(["tightness", "budget_s"])},
              "cv_by_family": ev_family, "cv_by_size": ev_size, "feature_importances_full_fit": importances,
              "max_runtime_s": float(raw["runtime_seconds"].max())}
    (out / "evaluation.json").write_text(json.dumps(report, indent=2, default=str))

    md = [f"# Selector evaluation (SYNTHETIC data, {len(raw)} runs, {len(cases)} cases)", "",
          "Label = engine with the lowest distance among feasible runs (ties -> OR-Tools, then hybrid).",
          "Regret = % extra distance over the best engine on the case. A failed choice (no feasible plan) is "
          "counted under 'Failed choices' and left out of the regret means.", "",
          f"Label counts: {report['label_counts']}", "",
          "## Leave-one-family-out CV (uniform / clustered / mixed)", "", table(ev_family), "",
          "Per fold: " + "; ".join(f"{f['held_out']}: acc {f['accuracy']:.3f}, regret {f['mean_regret_pct']:.2f}%"
                                   for f in ev_family["folds"]), "",
          "## Leave-one-size-out CV (20 / 50 / 80 customers)", "", table(ev_size), "",
          "Per fold: " + "; ".join(f"{f['held_out']}: acc {f['accuracy']:.3f}, regret {f['mean_regret_pct']:.2f}%"
                                   for f in ev_size["folds"]), "",
          "## Feature importances (tree fitted on all cases)", "",
          ", ".join(f"{k} {v:.2f}" for k, v in importances.items() if v > 0), "",
          f"Longest run: {report['max_runtime_s']:.2f} s."]
    (out / "evaluation.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
