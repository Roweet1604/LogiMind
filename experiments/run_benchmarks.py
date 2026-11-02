"""Repeatable benchmark runner.

Example (from the repository root):
    python experiments/run_benchmarks.py --sizes 10 25 50 --ga-seeds 5 --time-budget 10 --out experiments/results/run1

Fairness rule: OR-Tools and every GA run get the same wall-clock budget
(--time-budget seconds) on the same instance object / distance matrix.
Outputs: raw.csv, summary.csv, manifest.json, instances/<id>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.export import summarize, write_raw_csv  # noqa: E402
from app.services.generator import generate_instance  # noqa: E402
from app.services.runner import environment_info, run_algorithm  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[10, 25, 50])
    ap.add_argument("--instances-per-size", type=int, default=1)
    ap.add_argument("--ga-seeds", type=int, default=5, help="number of GA seeds (0..k-1) per instance")
    ap.add_argument("--ortools-repeats", type=int, default=1)
    ap.add_argument("--time-budget", type=float, default=10.0, help="seconds per run, same for both algorithms")
    ap.add_argument("--metric", choices=["euclidean", "haversine"], default="haversine")
    ap.add_argument("--population", type=int, default=100)
    ap.add_argument("--out", type=Path, default=Path("experiments/results/latest"))
    args = ap.parse_args(argv)

    out: Path = args.out
    (out / "instances").mkdir(parents=True, exist_ok=True)
    records = []
    for n in args.sizes:
        for k in range(args.instances_per_size):
            inst = generate_instance(n, seed=n * 1000 + k, metric=args.metric)
            (out / "instances" / f"{inst.instance_id}.json").write_text(json.dumps(inst.to_dict(), indent=1))
            for _ in range(args.ortools_repeats):
                records.append(run_algorithm(inst, "ortools", {"time_limit_s": args.time_budget}))
            for seed in range(args.ga_seeds):
                records.append(run_algorithm(inst, "ga", {
                    "seed": seed, "population_size": args.population, "max_generations": 10**9,
                    "time_limit_s": args.time_budget, "stagnation_generations": None}))
            last = records[-1].to_row()
            print(f"n={n} inst={inst.instance_id} done ({len(records)} runs so far; last={last['algorithm']} {last['status']})")

    raw = write_raw_csv(records, out / "raw.csv")
    summarize(raw).to_csv(out / "summary.csv", index=False)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "environment": environment_info(),
        "budget_policy": "identical wall-clock limit per run for OR-Tools and GA; GA stops on time only",
        "runs": len(records),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {out}/raw.csv, summary.csv, manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
