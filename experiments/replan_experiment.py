"""P7: warm vs cold replanning on SYNTHETIC instances, one guarded run at a time.

For each synthetic instance: a base plan (OR-Tools, 2 s), then three disruptions:
* vehicle_breakdown of the busiest vehicle,
* failed_delivery (retry) of the next stop on the busiest vehicle,
* urgent_order at a random point (loose window on time-window instances).
A third of every route counts as completed (frozen). Each disruption is replanned with OR-Tools
warm (current plan as initial assignment) and cold, at 0.5 s and 2 s. Separately, an urgent order
before dispatch (nothing frozen) is replanned with the GA seeded from the current plan vs unseeded.

Recorded per run: validator + frozen-stop check verdict, distance, time from the disruption to a
validated plan (event applied -> solver -> validation, through the guard), OR-Tools time to the first
solution, warm-start outcome, and how many unfinished stops changed vehicle (plan stability).

Usage: python experiments/replan_experiment.py --estimate-only | --out experiments/results/replan_2026-11-04
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.benchmarks.audit import git_commit  # noqa: E402
from app.evaluation.metrics import compute_metrics  # noqa: E402
from app.evaluation.validator import validate_routes  # noqa: E402
from app.replan import events as E  # noqa: E402
from app.replan.jobs import build_job, routes_by_vehicle  # noqa: E402
from app.selector.generator import FAMILIES, generate_family_instance  # noqa: E402
from app.services.guard import GuardedWorker  # noqa: E402
from app.services.runner import environment_info  # noqa: E402

N = 40
TIGHT = ["none", "loose"]
BASE_BUDGET = 2.0
BUDGETS = [0.5, 2.0]
OVERHEAD_S = 0.3


def instances():
    return [(f, t, generate_family_instance(f, N, t, seed=11)) for f in FAMILIES for t in TIGHT]


def plan_jobs() -> list[tuple]:
    jobs = []
    for f, t, _ in instances():
        for ev in ("vehicle_breakdown", "failed_delivery", "urgent_order"):
            for b in BUDGETS:
                for warm in (True, False):
                    jobs.append((f, t, ev, "ortools", b, warm))
        for b in BUDGETS:
            for warm in (True, False):
                jobs.append((f, t, "urgent_order_predispatch", "ga", b, warm))
    return jobs


def make_event(kind: str, inst, routes, rng):
    busiest = max(range(len(routes)), key=lambda v: len(routes[v]))
    completed = {v: len(r) // 3 for v, r in enumerate(routes) if r}
    if kind == "vehicle_breakdown":
        return E.VehicleBreakdown(type=kind, vehicle=busiest, completed=completed)
    if kind == "failed_delivery":
        return E.FailedDelivery(type=kind, customer_id=routes[busiest][completed[busiest]], completed=completed)
    cust = {"id": 1000, "x": rng.uniform(0, 100), "y": rng.uniform(0, 100), "demand": 1}
    if inst.has_time_windows:
        cust.update(ready_time=0.0, due_time=900.0, service_time=10.0)
    return E.UrgentOrder(type="urgent_order", customer=cust,
                       completed={} if kind == "urgent_order_predispatch" else completed)


def moved(old_routes, new_routes, frozen) -> int:
    old = {c: v for v, r in enumerate(old_routes) for c in r[len(frozen[v]):]}
    new = {c: v for v, r in enumerate(new_routes) for c in r}
    return sum(1 for c, v in old.items() if c in new and new[c] != v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "experiments" / "results" / "replan_2026-11-04"))
    ap.add_argument("--estimate-only", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=15.0)
    args = ap.parse_args()
    jobs = plan_jobs()
    n_inst = len(FAMILIES) * len(TIGHT)
    est = n_inst * (BASE_BUDGET + OVERHEAD_S) + sum(b + OVERHEAD_S for *_, b, _ in jobs)
    print(f"{n_inst} base plans + {len(jobs)} replans, estimated solver time {est / 60:.1f} min")
    if args.estimate_only:
        return
    if est > args.max_minutes * 60:
        sys.exit(f"estimate above --max-minutes {args.max_minutes}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env, commit = environment_info(), git_commit(ROOT)
    (out / "manifest.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data": "synthetic",
        "n_customers": N, "families": FAMILIES, "tightness": TIGHT, "base_budget_s": BASE_BUDGET,
        "budgets": BUDGETS, "estimate_min": round(est / 60, 2), "env": env, "git_commit": commit,
        "note": "frozen = first third of every route; uncommitted P7 code if git_commit is the P6 commit"}, indent=2))
    worker = GuardedWorker()
    rows = []
    t0 = time.perf_counter()
    try:
        bases = {}
        for f, t, inst in instances():
            rec = worker.run(inst, "ortools", {"time_limit_s": BASE_BUDGET})
            ok = rec.validation is not None and rec.validation.feasible
            bases[(f, t)] = (inst, rec.result.routes if ok else None)
            print(f"base {f}/{t}: {rec.result.status} feasible={ok}", flush=True)
        for k, (f, t, kind, engine, budget, warm) in enumerate(jobs, 1):
            inst, routes = bases[(f, t)]
            row = {"family": f, "tightness": t, "event": kind, "engine": engine, "budget_s": budget, "warm": warm,
                   "data_label": "synthetic", "git_commit": commit, "python": env["python"],
                   "ortools_version": env["ortools"]}
            if routes is None:
                rows.append({**row, "status": "no_base_plan"})
                continue
            routes = routes + [[] for _ in range(inst.vehicle_count - len(routes))]
            event = make_event(kind, inst, routes, random.Random(f"{f}{t}"))
            received = time.perf_counter()
            setup = E.apply_event(inst, routes, event)
            job = build_job(setup, engine, budget, warm_start=warm, seed=0)
            rec = worker.run(job.instance, job.algorithm, job.config)
            feasible, dist, problems, mv = False, None, [], None
            if rec.result.routes is not None:
                new = routes_by_vehicle(job, rec.result.routes, setup.instance.vehicle_count)
                val = validate_routes(setup.instance, new)
                problems = E.check_replan(new, setup)
                feasible = val.feasible and not problems
                dist = compute_metrics(setup.instance, new, val).total_distance
                mv = moved(routes, new, setup.frozen)
            done = time.perf_counter()
            diag = rec.result.diagnostics or {}
            row.update(status=rec.result.status, feasible=feasible, total_distance=dist,
                       replan_violations=len(problems), solver_seconds=rec.result.runtime_seconds,
                       disruption_to_feasible_s=round(done - received, 4) if feasible else None,
                       first_solution_s=diag.get("first_solution_s"), warm_start_result=diag.get("warm_start"),
                       warm_given=job.warm_start, stops_changed_vehicle=mv,
                       frozen_stops=sum(len(x) for x in setup.frozen), seed=0)
            rows.append(row)
            print(f"[{k}/{len(jobs)}] {f}/{t} {kind} {engine} b={budget} warm={warm}: {row['status']} "
                  f"feasible={feasible} dist={dist} warm_result={row['warm_start_result']}", flush=True)
    finally:
        worker.close()
    keys = sorted({k for r in rows for k in r})
    with (out / "raw.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"done in {(time.perf_counter() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
