"""What a worker does with a claimed job (P6 queue, decision 0021).

The solve itself still runs in the guarded solver process (services/guard.py), so a frozen run is killed at
its hard limit and stored as `hard_timeout`. Results go through the independent validator exactly as before.
Plan results are written through a TENANT session for the job's tenant, so a job can only ever change a plan
of its own tenant. Webhooks are sent by the worker's notifier after the plan row is committed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Plan, utcnow
from app.evaluation.metrics import compute_metrics
from app.evaluation.validator import validate_routes
from app.jobs.queue import JobView
from app.models.problem import Instance
from app.replan.events import check_replan
from app.replan.jobs import build_job, routes_by_vehicle, setup_from
from app.services.guard import GuardedWorker
from app.services.notify import WebhookNotifier
from app.services.plans import audit, cfg_engine
from app.services.store import _clean


class JobError(RuntimeError):
    """The job cannot be run (its plan is missing for its tenant, unknown kind, bad payload)."""


class JobExecutor:
    def __init__(self, factory: sessionmaker[Session], guard: GuardedWorker | None = None,
                 notifier: WebhookNotifier | None = None):
        self.factory = factory
        self.guard = guard or GuardedWorker()
        self.notifier = notifier

    def run(self, job: JobView) -> tuple[str, dict | None, str | None]:
        """(job state, job result, error). Plan outcomes are written to the plan row here."""
        if job.kind == "benchmark":
            return self._benchmark(job)
        if job.kind not in ("plan", "replan") or not job.tenant_id or not job.plan_id:
            raise JobError(f"malformed job {job.id}: kind={job.kind!r}")
        with self._tenant(job) as s:
            plan = s.get(Plan, job.plan_id)  # tenant-filtered: another tenant's plan is invisible here
            if plan is None:
                raise JobError(f"plan {job.plan_id} not found for tenant {job.tenant_id}")
            plan.state = "running"
            instance = Instance.from_dict(plan.instance)
            replan_record = dict(plan.replan or {})
            s.commit()
        if job.kind == "plan":
            return self._plan(job, instance)
        return self._replan(job, instance, replan_record)

    def _tenant(self, job: JobView):
        from app.db.session import tenant_session
        return tenant_session(self.factory, job.tenant_id)

    # ---- plan --------------------------------------------------------------------------------
    def _plan(self, job: JobView, instance: Instance):
        algorithm, cfg = job.payload["algorithm"], job.payload["config"]
        update: dict[str, Any]
        try:
            rec = self.guard.run(instance, algorithm, cfg)
            rec.result.run_id = job.plan_id
            update = {"state": "completed", "error": None, "result": _clean({
                "solve": rec.result.to_dict(),
                "validation": rec.validation.to_dict() if rec.validation else None,
                "metrics": rec.metrics.to_dict() if rec.metrics else None, "config": cfg})}
        except Exception as exc:  # reported, never hidden
            update = {"state": "failed", "error": f"{type(exc).__name__}: {exc}", "result": None}
        status = (update["result"] or {}).get("solve", {}).get("status")
        self._store(job, update, f"plan.{update['state']}", status=status)
        if self.notifier is not None:
            validation = (update["result"] or {}).get("validation") or {}
            self.notifier.emit(job.tenant_id, f"plan.{update['state']}", job.plan_id,
                               {"plan_id": job.plan_id, "state": update["state"], "status": status,
                                "feasible": validation.get("feasible") if update["result"] else None,
                                "engine": cfg_engine(algorithm), "error": update["error"]})
        return update["state"], None, update["error"]

    # ---- replan ------------------------------------------------------------------------------
    def _replan(self, job: JobView, instance: Instance, record: dict[str, Any]):
        p = job.payload
        timing: dict[str, Any] = {}
        feasible = False
        rjob = None
        try:
            setup = setup_from(instance, p["setup"])
            rjob = build_job(setup, p["engine"], p["time_limit_s"], p["warm_start"], p["seed"])
            rec = self.guard.run(rjob.instance, rjob.algorithm, rjob.config)
            rec.result.run_id = job.plan_id
            hidden = ("initial_routes", "initial_tours", "frozen")
            result: dict[str, Any] = {"solve": rec.result.to_dict(),
                                      "config": {k: v for k, v in rjob.config.items() if k not in hidden}}
            if rec.result.routes is not None:
                routes = routes_by_vehicle(rjob, rec.result.routes, setup.instance.vehicle_count)
                validation = validate_routes(setup.instance, routes)  # the real instance, not the solver's copy
                problems = check_replan(routes, setup)
                feasible = validation.feasible and not problems
                result.update(routes=routes, validation=validation.to_dict(), replan_violations=problems,
                              feasible=feasible,
                              metrics=compute_metrics(setup.instance, routes, validation).to_dict())
            else:
                result.update(routes=None, validation=None, replan_violations=[], feasible=False, metrics=None)
            # wall clock: the request was received by the API process, the result is made here
            elapsed = (utcnow() - datetime.fromisoformat(record["received_at"])).total_seconds()
            diag = rec.result.diagnostics or {}
            timing = {"solver_seconds": rec.result.runtime_seconds, "first_solution_s": diag.get("first_solution_s"),
                      "warm_start_result": diag.get("warm_start"), "attempts": job.attempts,
                      "disruption_to_result_s": round(elapsed, 3),
                      "disruption_to_feasible_s": round(elapsed, 3) if feasible else None}
            update = {"state": "completed", "error": None, "result": _clean(result)}
        except Exception as exc:  # reported, never hidden
            update = {"state": "failed", "error": f"{type(exc).__name__}: {exc}", "result": None}
        status = ((update["result"] or {}).get("solve") or {}).get("status")
        action = "plan.replanned" if update["state"] == "completed" else "plan.failed"
        self._store(job, update, action, status=status, feasible=feasible, timing=timing)
        if self.notifier is not None:
            self.notifier.emit(job.tenant_id, action, job.plan_id,
                               {"plan_id": job.plan_id, "state": update["state"], "status": status,
                                "feasible": feasible, "engine": rjob.algorithm if rjob else p.get("engine"),
                                "error": update["error"],
                                "disruption_to_feasible_s": timing.get("disruption_to_feasible_s")})
        return update["state"], None, update["error"]

    # ---- benchmark (research runs, no tenant) ---------------------------------------------------
    def _benchmark(self, job: JobView):
        p = job.payload
        rec = self.guard.run(Instance.from_dict(p["instance"]), p["algorithm"], p["config"])
        return "completed", _clean({
            "started_at": rec.started_at, "result": rec.result.to_dict(),
            "validation": rec.validation.to_dict() if rec.validation else None,
            "metrics": rec.metrics.to_dict() if rec.metrics else None, "row": rec.to_row()}), None

    # ---- bookkeeping -------------------------------------------------------------------------
    def _store(self, job: JobView, update: dict[str, Any], action: str, timing: dict | None = None, **detail):
        with self._tenant(job) as s:
            plan = s.get(Plan, job.plan_id)
            for k, v in update.items():
                setattr(plan, k, v)
            if timing is not None:
                plan.replan = _clean({**(plan.replan or {}), "timing": timing})
            plan.finished_at = utcnow()
            audit(s, job.tenant_id, "system", action, job.plan_id, job_id=job.id, attempt=job.attempts, **detail)
            s.commit()

    def fail_plan(self, job: JobView, error: str) -> None:
        """A job that could not run to the end (worker crashed too often, or JobError): its plan says so."""
        if job.kind == "benchmark" or not job.tenant_id or not job.plan_id:
            return
        with self._tenant(job) as s:
            plan = s.get(Plan, job.plan_id)
            if plan is None:  # not this tenant's plan: nothing may be written
                return
            plan.state, plan.error, plan.finished_at = "failed", error, datetime.now(timezone.utc)
            audit(s, job.tenant_id, "system", "plan.failed", job.plan_id, job_id=job.id, error=error)
            s.commit()
        if self.notifier is not None:
            self.notifier.emit(job.tenant_id, "plan.failed", job.plan_id,
                               {"plan_id": job.plan_id, "state": "failed", "status": None, "feasible": None,
                                "engine": None, "error": error})
