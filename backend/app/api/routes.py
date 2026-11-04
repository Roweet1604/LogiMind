from __future__ import annotations

import io
import os

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.api import schemas as S
from app.api.auth import require_principal
from app.benchmarks import catalog
from app.db.keys import Principal
from app.db.session import tenant_session
from app.models.problem import Customer, Instance, InstanceValidationError
from app.replan.events import ReplanError, ReplanIn
from app.services.export import summarize
from app.services.generator import generate_instance
from app.services.order_import import ImportFileError, parse_orders
from app.services.plans import PlanStateError, audit
from app.services.runner import environment_info
from app.services.store import Store

router = APIRouter(prefix="/api")
RESEARCH_TAG = "research (dev only, off by default)"
LEGACY_ENV = "LOGIMIND_DEV_RESEARCH_ENDPOINTS"


def legacy_open_from_env() -> bool:
    return os.environ.get(LEGACY_ENV) == "1"


def legacy_gate(request: Request) -> None:
    """The research endpoints (instances, runs, experiments, benchmarks) keep their data in a store with no
    tenants, so they are OFF unless the dev-only setting LOGIMIND_DEV_RESEARCH_ENDPOINTS=1 is set
    (decision 0011). Tenants use /api/plans, /api/orders/import, /api/webhooks and /api/audit."""
    if not request.app.state.legacy_open:
        raise HTTPException(403, detail=f"research endpoints are disabled; they are for local development only "
                                        f"(set {LEGACY_ENV}=1). Use /api/plans with an API key.")


RESEARCH = {"dependencies": [Depends(legacy_gate)], "tags": [RESEARCH_TAG]}


def store_of(request: Request) -> Store:
    return request.app.state.store


def max_time_limit() -> float:
    return float(os.environ.get("ROUTEOPT_MAX_TIME_LIMIT_S", "300"))


def check_time(value: float | None, field: str) -> None:
    if value is not None and value > max_time_limit():
        raise HTTPException(422, detail={"message": f"{field} must be <= {max_time_limit()} s", "errors": []})


def instance_summary(i: Instance) -> dict:
    return {"instance_id": i.instance_id, "name": i.name, "source": i.source, "metric": i.metric,
            "n_customers": len(i.customers), "vehicle_count": i.vehicle_count,
            "vehicle_capacity": i.vehicle_capacity, "has_time_windows": i.has_time_windows}


def register(request: Request, inst: Instance) -> dict:
    try:
        inst.validate()
    except InstanceValidationError as exc:
        raise HTTPException(422, detail={"message": "invalid instance", "errors": exc.errors})
    store_of(request).add_instance(inst)
    return inst.to_dict()


def csv_response(rows: list[dict], filename: str, df: pd.DataFrame | None = None) -> Response:
    df = df if df is not None else pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": environment_info()}


# ---- instances ----------------------------------------------------------
@router.post("/instances", status_code=201, **RESEARCH)
def create_instance(body: S.InstanceIn, request: Request) -> dict:
    return register(request, instance_from(body))


def instance_from(body: S.InstanceIn) -> Instance:
    return Instance(
        depot_x=body.depot_x, depot_y=body.depot_y,
        customers=[Customer(c.id, c.x, c.y, c.demand, ready_time=c.ready_time, due_time=c.due_time,
                            service_time=c.service_time) for c in body.customers],
        vehicle_count=body.vehicle_count, vehicle_capacity=body.vehicle_capacity, metric=body.metric,
        distance_unit=body.distance_unit, fixed_vehicle_cost=body.fixed_vehicle_cost,
        cost_per_distance=body.cost_per_distance, name=body.name or "user-instance", source="user",
        depot_ready_time=body.depot_ready_time, depot_due_time=body.depot_due_time,
        time_per_distance=body.time_per_distance, time_unit=body.time_unit)


@router.post("/instances/generate", status_code=201, **RESEARCH)
def generate(body: S.GenerateIn, request: Request) -> dict:
    if body.demand_min > body.demand_max:
        raise HTTPException(422, detail={"message": "demand_min must be <= demand_max", "errors": []})
    inst = generate_instance(
        body.n_customers, seed=body.seed, metric=body.metric, demand_range=(body.demand_min, body.demand_max),
        vehicle_capacity=body.vehicle_capacity, vehicle_count=body.vehicle_count,
        fixed_vehicle_cost=body.fixed_vehicle_cost, cost_per_distance=body.cost_per_distance)
    return register(request, inst)


# ---- public benchmarks ---------------------------------------------------
@router.get("/benchmarks", **RESEARCH)
def list_benchmarks() -> list[dict]:
    """Best-known solutions table, with whether the instance file is downloaded."""
    out = []
    for name, b in sorted(catalog.load_bks().items()):
        row = dict(b.__dict__)
        row["downloaded"] = b.set in catalog.SETS and catalog.data_file(b.set, name).exists()
        out.append(row)
    return out


@router.post("/benchmarks/{set_key}/{name}", status_code=201, **RESEARCH)
def load_benchmark(set_key: str, name: str, request: Request) -> dict:
    if set_key not in catalog.SETS or not catalog.re_safe_name(name):
        raise HTTPException(404, detail=f"unknown benchmark {set_key}/{name}")
    try:
        inst = catalog.load_instance(set_key, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc))
    out = register(request, inst)
    bks = catalog.load_bks().get(name)
    out["best_known"] = dict(bks.__dict__) if bks else None
    return out


@router.get("/instances", **RESEARCH)
def list_instances(request: Request) -> list[dict]:
    return [instance_summary(i) for i in store_of(request).instances.values()]


@router.get("/instances/{instance_id}", **RESEARCH)
def get_instance(instance_id: str, request: Request) -> dict:
    inst = store_of(request).instances.get(instance_id)
    if inst is None:
        raise HTTPException(404, detail=f"instance {instance_id} not found")
    return inst.to_dict()


# ---- runs ---------------------------------------------------------------
HYBRID_OWN = {"time_limit_s", "local_search", "seed", "max_generations", "stagnation_generations"}


def solver_config(algorithm: str, time_limit_s: float | None, ortools: S.ORToolsParams, ga: S.GAParams,
                  hybrid: S.HybridParams | None = None) -> dict:
    if algorithm == "ortools":
        return {"time_limit_s": time_limit_s or 10.0, **ortools.model_dump()}
    if algorithm == "hybrid":
        hp = hybrid or S.HybridParams()
        return {"time_limit_s": time_limit_s or 10.0, **hp.model_dump(), **ortools.model_dump(),
                "seed": ga.seed, "ga": {k: v for k, v in ga.model_dump().items() if k not in HYBRID_OWN}}
    return {**ga.model_dump(), "time_limit_s": time_limit_s}


@router.post("/runs", status_code=202, **RESEARCH)
def start_run(body: S.RunIn, request: Request) -> dict:
    store = store_of(request)
    if body.instance_id not in store.instances:
        raise HTTPException(404, detail=f"instance {body.instance_id} not found")
    check_time(body.time_limit_s, "time_limit_s")
    run_id = store.submit_run(body.instance_id, body.algorithm,
                              solver_config(body.algorithm, body.time_limit_s, body.ortools, body.ga, body.hybrid))
    return {"run_id": run_id, "state": "queued"}


# ---- plans (P5 engine=auto, P6b tenant API) ----------------------------------
@router.post("/plans", status_code=202, tags=["plans"])
def create_plan(body: S.PlanIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Queue a plan for the caller's tenant. With engine="auto" the selector picks the engine and the
    reply explains the choice.

    The instance is sent inline and stored with the plan (tenant-owned). The solver's routes go through
    the independent validator; GET the plan for `feasible`, the solver status and the metrics. Timeouts
    and failures are reported as what they are.
    """
    check_time(body.time_limit_s, "time_limit_s")
    inst = instance_from(body.instance)
    try:
        inst.validate()
    except InstanceValidationError as exc:
        raise HTTPException(422, detail={"message": "invalid instance", "errors": exc.errors})
    return request.app.state.plans.submit(who, inst, body.engine, body.time_limit_s, body.seed)


@router.get("/plans/{plan_id}", tags=["plans"])
def get_plan(plan_id: str, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """One plan of the caller's tenant. Another tenant's plan gives the same 404 as a missing plan."""
    plan = request.app.state.plans.get(who, plan_id)
    if plan is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return plan


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.post("/plans/{plan_id}/replan", status_code=202, tags=["plans"])
def replan_plan(plan_id: str, body: ReplanIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Replan a completed, feasible plan after a disruption (vehicle_breakdown, failed_delivery, urgent_order).

    Completed stops (event.completed: vehicle -> stops done) are frozen. OR-Tools starts from the current plan
    (initial assignment); the GA, seeded with the current plan, is allowed only when no stop is frozen. The new
    plan is `feasible` only if it passes the validator AND the frozen-stop check. GET it for the result and
    replan.timing.disruption_to_feasible_s (time from receiving this request to a validated plan)."""
    check_time(body.time_limit_s, "time_limit_s")
    try:
        out = request.app.state.plans.replan(who, plan_id, body.event, body.engine, body.time_limit_s,
                                             body.warm_start, body.seed)
    except PlanStateError as exc:
        raise HTTPException(409, detail=str(exc))
    except (ReplanError, InstanceValidationError) as exc:
        raise HTTPException(422, detail=str(exc))
    if out is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return out


@router.post("/orders/import", tags=["orders"])
async def import_orders(request: Request, file: UploadFile = File(..., description=".csv or .xlsx"),
                        who: Principal = Depends(require_principal)) -> dict:
    """Validate an order file row by row. Columns: id, demand, x/y or lon/lat, optional ready_time,
    due_time, service_time. Returns every problem with its spreadsheet row number; `customers` is filled
    (ready for a plan's `instance.customers`) only when every row is valid. Nothing is stored."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail=f"file larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    try:
        report = parse_orders(file.filename or "", data).to_dict()
    except ImportFileError as exc:
        report = None
        error = str(exc)
    with tenant_session(request.app.state.db, who.tenant_id) as s:
        audit(s, who.tenant_id, who.key_id, "orders.import", file.filename or "",
              ok=bool(report and report["ok"]), rows=report["rows"] if report else 0)
        s.commit()
    if report is None:
        raise HTTPException(422, detail={"message": error, "issues": []})
    return report


@router.get("/runs", **RESEARCH)
def list_runs(request: Request, instance_id: str | None = None) -> list[dict]:
    keys = ("run_id", "instance_id", "algorithm", "state", "experiment_id", "created_at", "row", "error")
    return [{k: r.get(k) for k in keys} for r in store_of(request).list_runs(instance_id)]


@router.get("/runs/export", **RESEARCH)
def export_runs(request: Request) -> Response:
    rows = [r["row"] for r in store_of(request).list_runs() if r.get("row")]
    return csv_response(rows, "runs.csv")


@router.get("/runs/{run_id}", **RESEARCH)
def get_run(run_id: str, request: Request) -> dict:
    run = store_of(request).get_run(run_id)
    if run is None:
        raise HTTPException(404, detail=f"run {run_id} not found")
    return run


@router.get("/runs/{run_id}/metrics", **RESEARCH)
def get_run_metrics(run_id: str, request: Request) -> dict:
    run = get_run(run_id, request)
    if run["state"] not in ("completed", "failed"):
        raise HTTPException(409, detail=f"run {run_id} is {run['state']}")
    return {"run_id": run_id, "algorithm": run["algorithm"], "state": run["state"],
            "solver_status": (run["result"] or {}).get("status"),
            "feasible": (run["validation"] or {}).get("feasible"), "metrics": run["metrics"],
            "runtime_seconds": (run["result"] or {}).get("runtime_seconds")}


# ---- experiments --------------------------------------------------------
@router.post("/experiments", status_code=202, **RESEARCH)
def start_experiment(body: S.ExperimentIn, request: Request) -> dict:
    store = store_of(request)
    if body.instance_id not in store.instances:
        raise HTTPException(404, detail=f"instance {body.instance_id} not found")
    check_time(body.time_budget_s, "time_budget_s")
    jobs = [("ortools", solver_config("ortools", body.time_budget_s, body.ortools, body.ga))
            for _ in range(body.ortools_repeats)]
    for seed in range(body.ga_seeds):
        ga = body.ga.model_copy(update={"seed": seed, "max_generations": 1_000_000, "stagnation_generations": None})
        jobs.append(("ga", solver_config("ga", body.time_budget_s, body.ortools, ga)))
    params = {"time_budget_s": body.time_budget_s, "ga_seeds": body.ga_seeds,
              "ortools_repeats": body.ortools_repeats, "ga": body.ga.model_dump(),
              "ortools": body.ortools.model_dump(),
              "budget_policy": "identical wall-clock limit per run; GA stops on time only; runs execute one at a time"}
    exp_id = store.submit_experiment(body.instance_id, params, jobs)
    return {"experiment_id": exp_id, "state": "running", "runs": len(jobs)}


@router.get("/experiments", **RESEARCH)
def list_experiments(request: Request) -> list[dict]:
    store = store_of(request)
    out = []
    for exp_id in list(store.experiments):
        view = store.experiment_view(exp_id)
        inst = store.instances.get(view["instance_id"])
        out.append({
            "experiment_id": exp_id, "instance_id": view["instance_id"], "created_at": view["created_at"],
            "instance_name": inst.name if inst else None,
            "n_customers": len(inst.customers) if inst else None,
            "state": view["state"], "lost_runs": view["lost_runs"],
            "time_budget_s": view["params"]["time_budget_s"], "ga_seeds": view["params"]["ga_seeds"],
            "ortools_repeats": view["params"]["ortools_repeats"], "summary": view["summary"]})
    return sorted(out, key=lambda e: e["created_at"], reverse=True)


@router.get("/experiments/{experiment_id}", **RESEARCH)
def get_experiment(experiment_id: str, request: Request) -> dict:
    view = store_of(request).experiment_view(experiment_id)
    if view is None:
        raise HTTPException(404, detail=f"experiment {experiment_id} not found")
    return view


@router.get("/experiments/{experiment_id}/export", **RESEARCH)
def export_experiment(experiment_id: str, request: Request, kind: str = "raw") -> Response:
    if kind not in ("raw", "summary"):
        raise HTTPException(422, detail={"message": "kind must be 'raw' or 'summary'", "errors": []})
    rows = store_of(request).experiment_rows(experiment_id)
    if rows is None:
        raise HTTPException(404, detail=f"experiment {experiment_id} not found")
    if kind == "summary":
        df = summarize(pd.DataFrame(rows)) if rows else pd.DataFrame()
        return csv_response([], f"{experiment_id}_summary.csv", df)
    return csv_response(rows, f"{experiment_id}_raw.csv")
