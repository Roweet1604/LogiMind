"""P5: build the engine-selector dataset on SYNTHETIC instances.

Every (instance, budget) case runs each engine once, one run at a time, through the
wall-clock guard, with the same instance object and the same total budget (equal-clock
rule). Rows are appended to raw.csv after every run, so `--resume` continues an
interrupted run. All instances are synthetic (label `synthetic` in every row).

Usage (from the repo root):
  python experiments/selector_dataset.py --estimate-only
  python experiments/selector_dataset.py --out experiments/results/selector_2026-11-04 [--resume]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.benchmarks.audit import git_commit  # noqa: E402
from app.selector.dataset import ENGINE_CONFIGS, plan_cases  # noqa: E402
from app.selector.features import extract_features  # noqa: E402
from app.selector.generator import generate_family_instance  # noqa: E402
from app.services.guard import GuardedWorker  # noqa: E402
from app.services.runner import environment_info  # noqa: E402

SIZES = [20, 50, 80]
TIGHT = ["none", "loose", "tight"]
BUDGETS = [1.0, 3.0]
SEEDS = 2
OVERHEAD_S = 0.3  # per-run allowance for validation, IPC and model build (measured roughly in P3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "experiments" / "results" / "selector_2026-11-04"))
    ap.add_argument("--estimate-only", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=20.0, help="refuse to start above this estimate")
    args = ap.parse_args()

    cases = plan_cases(SIZES, TIGHT, BUDGETS, SEEDS)
    jobs = [(c, e) for c in cases for e in ENGINE_CONFIGS]
    est = sum(c["budget_s"] + OVERHEAD_S for c, _ in jobs)
    print(f"{len(cases)} cases, {len(jobs)} runs, estimated solver time {est / 60:.1f} min")
    if args.estimate_only:
        return
    if est > args.max_minutes * 60:
        sys.exit(f"estimate {est / 60:.1f} min is above --max-minutes {args.max_minutes}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "dataset_raw.csv"
    done: set[tuple] = set()
    if args.resume and raw.exists():
        with raw.open(newline="") as f:
            done = {(r["case_id"], r["engine"]) for r in csv.DictReader(f)}
    elif raw.exists():
        sys.exit(f"{raw} exists; use --resume or another --out")

    env, commit = environment_info(), git_commit(ROOT)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data": "synthetic",
                "sizes": SIZES, "tightness": TIGHT, "budgets": BUDGETS, "seeds": SEEDS,
                "engines": ENGINE_CONFIGS, "estimate_min": round(est / 60, 2), "env": env, "git_commit": commit,
                "resumed": bool(done)}
    (out / ("dataset_manifest_resume.json" if done else "dataset_manifest.json")).write_text(
        json.dumps(manifest, indent=2))

    worker = GuardedWorker()
    writer = None
    t_start = time.perf_counter()
    cache: dict[str, object] = {}
    try:
        with raw.open("a", newline="") as f:
            for k, (case, engine) in enumerate(jobs, start=1):
                if (case["case_id"], engine) in done:
                    continue
                ikey = case["instance_key"]
                if ikey not in cache:
                    cache[ikey] = generate_family_instance(case["family"], case["n_customers"],
                                                           case["tightness"], case["seed"])
                inst = cache[ikey]
                algorithm, cfg = ENGINE_CONFIGS[engine]
                cfg = {**cfg, "time_limit_s": case["budget_s"]}
                if algorithm != "ortools":
                    cfg["seed"] = case["seed"]
                rec = worker.run(inst, algorithm, cfg)
                row = rec.to_row()
                row.update({**case, "engine": engine, "data_label": "synthetic", "git_commit": commit,
                            "python": env["python"], "ortools_version": env["ortools"],
                            "numpy_version": env["numpy"], "platform": env["platform"]})
                row.update({f"f_{n}": v for n, v in extract_features(inst, case["budget_s"]).items()})
                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    if f.tell() == 0:
                        writer.writeheader()
                writer.writerow(row)
                f.flush()
                print(f"[{k}/{len(jobs)}] {case['case_id']} {engine}: {row['status']} "
                      f"feasible={row['feasible']} dist={row['total_distance']:.1f} t={row['runtime_seconds']:.2f}s",
                      flush=True)
    finally:
        worker.close()
    print(f"done in {(time.perf_counter() - t_start) / 60:.1f} min")


if __name__ == "__main__":
    main()
