"""OR-Tools configuration audit (Phase 2).

Grid: first-solution strategy x metaheuristic x time budget x repeats, on
benchmark (Solomon VRPTW, CVRPLIB A/X) and synthetic CVRP instances.
Runs are strictly one at a time. Rows are appended to raw.csv as they finish,
so an interrupted audit can continue with --resume.

Examples (from the repository root):
    python experiments/ortools_audit.py --estimate-only
    python experiments/ortools_audit.py --out experiments/results/ortools_audit
    python experiments/ortools_audit.py --out experiments/results/ortools_audit --resume
    python experiments/ortools_audit.py --out experiments/results/ortools_audit --analyze-only

Outputs: raw.csv (one row per run), summary.csv, variation.csv,
recommendations.csv, manifest.json, report.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

import pandas as pd  # noqa: E402

from app.benchmarks import audit as A  # noqa: E402
from app.services.runner import environment_info  # noqa: E402


def fmt(v: float, digits: int = 2) -> str:
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{digits}f}"


def write_report(df: pd.DataFrame, out: Path, manifest: dict) -> None:
    summary = A.summarize_configs(df)
    variation = A.repeat_variation(df)
    rec = A.recommend(summary)
    summary.to_csv(out / "summary.csv", index=False)
    variation.to_csv(out / "variation.csv", index=False)
    rec.to_csv(out / "recommendations.csv", index=False)

    env = manifest["environment"]
    lines = [
        "# OR-Tools audit report", "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from raw.csv ({len(df)} runs).",
        f"Machine: {env['processor']}, {env['cpu_count']} logical CPUs, {env['platform']}. "
        f"Python {env['python']}, OR-Tools {env['ortools']}. Git commit {manifest.get('git_commit', '?')}.", "",
        "Notes: synthetic instances are generated (labelled `synthetic:<n>`), not real data. "
        "`gap to BKS` uses the published best-known values in experiments/benchmarks/bks.csv. "
        "`gap to best observed` is against the best distance found anywhere in this audit, NOT a best-known value. "
        "OR-Tools has no seed: repeats re-run the same configuration; their differences come from the time limit. "
        "Gaps are averaged over feasible runs only; the `solved` column shows how many runs gave a feasible plan.", "",
        "## Recommended configuration per problem and budget", "",
        "| Problem | Budget (s) | Class | First solution | Metaheuristic | Mean gap to best observed % | Mean gap to BKS % | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, r in rec.iterrows():
        lines.append(f"| {r['problem']} | {fmt(r['budget_s'], 0)} | {r['budget_class']} | {r['first_solution']} | "
                     f"{r['metaheuristic']} | {fmt(r.get('mean_gap_best_observed_pct', math.nan))} | "
                     f"{fmt(r.get('mean_gap_bks_pct', math.nan))} | {r['note']} |")

    budgets = sorted(summary["budget_s"].unique())
    for problem in sorted(summary["problem"].unique()):
        s = summary[summary["problem"] == problem]
        lines += ["", f"## {problem}: every configuration at every budget", "",
                  "Cell = solved runs / runs, mean gap to best observed %, mean gap to BKS % (benchmarks only).", "",
                  "| First solution | Metaheuristic | " + " | ".join(f"{fmt(b, 0)} s" for b in budgets) + " |",
                  "| --- | --- | " + " | ".join("---" for _ in budgets) + " |"]
        for (fs, mh), g in s.groupby(A.CONFIG):
            cells = []
            for b in budgets:
                c = g[g["budget_s"] == b]
                if c.empty:
                    cells.append("not run")
                    continue
                c = c.iloc[0]
                cells.append(f"{c['feasible_runs']}/{c['runs']}, {fmt(c['mean_gap_best_observed_pct'])}, "
                             f"{fmt(c['mean_gap_bks_pct'])}")
            lines.append(f"| {fs} | {mh} | " + " | ".join(cells) + " |")

    anomalies = A.timing_anomalies(df)
    lines += ["", "## Timing anomalies (excluded from all statistics above and below)", "",
              f"Runs whose wall clock exceeded {A.ANOMALY_FACTOR}x their budget. They stay in raw.csv.", ""]
    if anomalies.empty:
        lines.append("None.")
    else:
        lines += ["| Instance | First solution | Metaheuristic | Budget (s) | Repeat | Runtime (s) | Started (UTC) |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for _, r in anomalies.iterrows():
            lines.append(f"| {r['instance_key']} | {r['first_solution']} | {r['metaheuristic']} | {fmt(r['budget_s'], 0)} | "
                         f"{r['repeat']} | {fmt(r['runtime_seconds'], 1)} | {r['started_at']} |")

    lines += ["", "## Failures (runs without a feasible plan)", ""]
    fails = df[df["feasible"].astype(str) != "True"]
    if fails.empty:
        lines.append("None.")
    else:
        lines += ["| Instance | First solution | Metaheuristic | Budget (s) | Failed runs | OR-Tools status |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for (k, fs, mh, b), g in fails.groupby(["instance_key", "first_solution", "metaheuristic", "budget_s"]):
            lines.append(f"| {k} | {fs} | {mh} | {fmt(b, 0)} | {len(g)} | "
                         f"{', '.join(sorted(set(g['ortools_status'].astype(str))))} |")

    v = variation.dropna(subset=["spread_pct"])
    lines += ["", "## Run-to-run variation (same configuration, repeated)", "",
              "Spread = (worst - best) / best distance over the feasible repeats, in %.", "",
              "| Problem | Metaheuristic | Budget (s) | Groups | Mean spread % | Max spread % | Groups with spread 0 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for (problem, mh, b), g in v.groupby(["problem", "metaheuristic", "budget_s"]):
        lines.append(f"| {problem} | {mh} | {fmt(b, 0)} | {len(g)} | {fmt(g['spread_pct'].mean(), 3)} | "
                     f"{fmt(g['spread_pct'].max(), 3)} | {int((g['spread_pct'] == 0).sum())} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", nargs="+", default=A.INSTANCES)
    ap.add_argument("--first-solutions", nargs="+", default=A.FIRST_SOLUTIONS)
    ap.add_argument("--metaheuristics", nargs="+", default=A.METAHEURISTICS)
    ap.add_argument("--budgets", type=float, nargs="+", default=A.BUDGETS)
    ap.add_argument("--repeats", type=int, default=A.REPEATS)
    ap.add_argument("--out", type=Path, default=REPO / "experiments" / "results" / "ortools_audit")
    ap.add_argument("--resume", action="store_true", help="skip runs already in out/raw.csv")
    ap.add_argument("--estimate-only", action="store_true")
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args(argv)

    out: Path = args.out
    raw = out / "raw.csv"
    jobs = A.plan_jobs(args.instances, args.first_solutions, args.metaheuristics, args.budgets, args.repeats)
    est = A.estimate_seconds(jobs)
    print(f"{len(jobs)} runs planned; estimated time ~{est / 60:.0f} min (time-bound runs at full budget, "
          f"GREEDY_DESCENT counted as 1 s; failures can add more)")
    if args.estimate_only:
        return 0

    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if not args.analyze_only:
        if raw.exists() and not args.resume:
            print(f"{raw} exists; use --resume to continue it or choose another --out", file=sys.stderr)
            return 2
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
            "environment": environment_info(), "git_commit": A.git_commit(REPO),
            "planned_runs": len(jobs), "estimated_seconds": est,
            "policy": "one run at a time; time limit = total wall clock incl. model build; "
                      "OR-Tools has no seed, repeats re-run the same configuration",
        }
        if args.resume and manifest_path.exists():  # keep the original start; log each resume
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            old.setdefault("resumed", []).append({k: manifest[k] for k in ("created_at", "environment", "git_commit")})
            manifest = old
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        done = A.done_keys(raw) if args.resume else set()
        t0, count = time.perf_counter(), 0
        writer = None
        with raw.open("a", newline="", encoding="utf-8") as f:
            for row in A.iter_runs(jobs, REPO, done):
                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    if f.tell() == 0:
                        writer.writeheader()
                writer.writerow(row)
                f.flush()
                count += 1
                if count % 25 == 0:
                    print(f"{count + len(done)}/{len(jobs)} runs, {time.perf_counter() - t0:.0f} s elapsed", flush=True)
        print(f"finished {count} new runs in {time.perf_counter() - t0:.0f} s")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    df = pd.read_csv(raw)
    write_report(df, out, manifest)
    print(f"wrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
