"""Engine comparison + ablation (Phase 3): OR-Tools, GA and the hybrid under the
equal-clock rule. Runs one at a time through the wall-clock guard; rows are
appended to raw.csv as they finish (use --resume after an interruption).

Examples (from the repository root):
    python experiments/compare_engines.py --estimate-only
    python experiments/compare_engines.py --out %TEMP%/compare
    python experiments/compare_engines.py --out %TEMP%/compare --resume
    python experiments/compare_engines.py --out %TEMP%/compare --analyze-only

Outputs: raw.csv, summary.csv, per_instance.csv, manifest.json, report.md.
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
from app.benchmarks import compare as C  # noqa: E402
from app.benchmarks.audit import git_commit, timing_anomalies  # noqa: E402
from app.services.runner import environment_info  # noqa: E402


def fmt(v, digits: int = 2) -> str:
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{digits}f}"


def write_report(df: pd.DataFrame, out: Path, manifest: dict) -> None:
    summary, inst = C.summarize(df), C.per_instance(df)
    summary.to_csv(out / "summary.csv", index=False)
    inst.to_csv(out / "per_instance.csv", index=False)
    env = manifest["environment"]
    budgets = sorted(summary["budget_s"].unique())
    lines = [
        "# Engine comparison and ablation (P3)", "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from raw.csv ({len(df)} runs). "
        f"Machine: {env['processor']}, {env['cpu_count']} logical CPUs. Python {env['python']}, "
        f"OR-Tools {env['ortools']}. Git commit {manifest.get('git_commit', '?')}.", "",
        "Equal-clock rule: every method gets the same total wall-clock budget on the same instance "
        "(the hybrid's OR-Tools phase is inside its budget). Gaps are averaged over feasible runs only; "
        "`solved` shows feasible runs / runs. `gap to BKS` uses published best-known values (benchmarks only); "
        "`gap to best observed` is against the best distance found in this experiment (not a best-known value). "
        "Synthetic instances are generated. OR-Tools has no seed: its repeats are re-runs.", "",
        "Methods: " + "; ".join(f"`{m}` = {C.LABELS[m]}" for m in C.METHODS) + ".",
    ]
    for problem in sorted(summary["problem"].unique()):
        s = summary[summary["problem"] == problem]
        lines += ["", f"## {problem}", "",
                  "Cell = solved / runs, mean gap to BKS %, mean gap to best observed %.", "",
                  "| Method | " + " | ".join(f"{fmt(b, 0)} s" for b in budgets) + " |",
                  "| --- | " + " | ".join("---" for _ in budgets) + " |"]
        for m in C.METHODS:
            cells = []
            for b in budgets:
                c = s[(s["method"] == m) & (s["budget_s"] == b)]
                if c.empty:
                    cells.append("not run")
                    continue
                c = c.iloc[0]
                cells.append(f"{c['feasible_runs']}/{c['runs']}, {fmt(c['mean_gap_bks_pct'])}, "
                             f"{fmt(c['mean_gap_best_observed_pct'])}")
            lines.append(f"| {m} | " + " | ".join(cells) + " |")

    lines += ["", "## Per instance: solved runs and mean routes used (vehicle limit in brackets)", "",
              "| Instance | Budget (s) | " + " | ".join(C.METHODS) + " |",
              "| --- | --- | " + " | ".join("---" for _ in C.METHODS) + " |"]
    for (key, b), g in inst.groupby(["instance_key", "budget_s"]):
        g = g.set_index("method")
        cells = [f"{int(g.loc[m, 'feasible_runs'])}/{int(g.loc[m, 'runs'])}, {fmt(g.loc[m, 'mean_routes'], 1)} "
                 f"({int(g.loc[m, 'vehicle_limit'])})" if m in g.index else "-" for m in C.METHODS]
        lines.append(f"| {key} | {fmt(b, 0)} | " + " | ".join(cells) + " |")

    hyb = df[df["method"].str.startswith("hybrid")]
    if not hyb.empty:
        imp = hyb["hybrid_improved_over_seed"].astype(str) == "True"
        lines += ["", "## Did the GA phase improve the OR-Tools seed?", "",
                  "| Method | Budget (s) | Runs | Improved over seed |", "| --- | --- | --- | --- |"]
        for (m, b), g in hyb.assign(imp=imp).groupby(["method", "budget_s"]):
            lines.append(f"| {m} | {fmt(b, 0)} | {len(g)} | {int(g['imp'].sum())} |")

    timeouts = df[df["status"] == "hard_timeout"]
    anomalies = timing_anomalies(df)
    lines += ["", "## Hard timeouts and timing anomalies (excluded from the tables above)", ""]
    if anomalies.empty:
        lines.append("None.")
    else:
        lines += [f"{len(timeouts)} runs stopped by the wall-clock guard; {len(anomalies)} runs above 1.5x budget.", "",
                  "| Instance | Method | Budget (s) | Seed | Status | Runtime (s) |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for _, r in anomalies.iterrows():
            lines.append(f"| {r['instance_key']} | {r['method']} | {fmt(r['budget_s'], 0)} | {r['seed']} | "
                         f"{r['status']} | {fmt(r['runtime_seconds'], 1)} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", nargs="+", default=C.INSTANCES)
    ap.add_argument("--methods", nargs="+", default=list(C.METHODS), choices=list(C.METHODS))
    ap.add_argument("--budgets", type=float, nargs="+", default=C.BUDGETS)
    ap.add_argument("--seeds", type=int, default=C.SEEDS)
    ap.add_argument("--out", type=Path, default=REPO / "experiments" / "results" / "compare")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--estimate-only", action="store_true")
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args(argv)

    out, raw = args.out, args.out / "raw.csv"
    jobs = C.plan_jobs(args.instances, args.methods, args.budgets, args.seeds)
    est = C.estimate_seconds(jobs)
    print(f"{len(jobs)} runs planned; estimated time ~{est / 60:.0f} min (every run uses its full budget)")
    if args.estimate_only:
        return 0
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if not args.analyze_only:
        if raw.exists() and not args.resume:
            print(f"{raw} exists; use --resume or another --out", file=sys.stderr)
            return 2
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
                    "environment": environment_info(), "git_commit": git_commit(REPO),
                    "planned_runs": len(jobs), "estimated_seconds": est,
                    "methods": {m: {"algorithm": a, "config": c, "label": C.LABELS[m]}
                                for m, (a, c) in C.METHODS.items()},
                    "policy": "equal total wall clock per run; one run at a time; wall-clock guard "
                              "(1.5 x budget + 5 s) stops hung runs as hard_timeout"}
        if args.resume and manifest_path.exists():
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            old.setdefault("resumed", []).append({k: manifest[k] for k in ("created_at", "environment", "git_commit")})
            manifest = old
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        done = set()
        if args.resume and raw.exists():
            d = pd.read_csv(raw)
            done = {(r.instance_key, r.method, float(r.budget_s), int(r.seed)) for r in d.itertuples()}
        t0, count, writer = time.perf_counter(), 0, None
        with raw.open("a", newline="", encoding="utf-8") as f:
            for row in C.iter_runs(jobs, REPO, done):
                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    if f.tell() == 0:
                        writer.writeheader()
                writer.writerow(row)
                f.flush()
                count += 1
                if count % 10 == 0:
                    print(f"{count + len(done)}/{len(jobs)} runs, {time.perf_counter() - t0:.0f} s elapsed", flush=True)
        print(f"finished {count} new runs in {time.perf_counter() - t0:.0f} s")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    write_report(pd.read_csv(raw), out, manifest)
    print(f"wrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
