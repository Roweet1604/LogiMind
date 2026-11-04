"""Tenant plans: stored in the database, solved on the store's single solver thread.

Plans share the store's one worker thread and guarded worker process with the
research runs, so solver jobs still run one at a time. Every plan's routes go
through the independent validator; `feasible` is the validator's verdict, and
timeouts or failures are stored as what they are.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.keys import Principal
from app.db.models import AuditLog, Plan, utcnow
from app.db.session import tenant_session
from app.evaluation.metrics import compute_metrics
from app.evaluation.validator import validate_routes
from app.models.problem import Instance
from app.replan.events import apply_event, check_replan
from app.replan.jobs import build_job, routes_by_vehicle
from app.selector.dataset import ENGINE_CONFIGS
from app.selector.model import ENGINE_LABELS, get_selector
from app.services.notify import WebhookNotifier
from app.services.store import Store, _clean

API_ENGINE = {"ortools": "ortools", "hybrid": "hybrid", "ga": "ga_ls"}  # the API's "ga" is GA + local search


class PlanStateError(ValueError):
    """The plan exists but cannot be replanned (not finished, or not feasible)."""


def cfg_engine(algorithm: str) -> str:
    return {"ga": "ga_ls"}.get(algorithm, algorithm)


def audit(s: Session, tenant_id: str, actor: str, action: str, target: str = "", **detail: Any) -> None:
    s.add(AuditLog(tenant_id=tenant_id, actor=actor, action=action, target=target, detail=_clean(detail) or None))


class PlanService:
    def __init__(self, factory: sessionmaker[Session], store: Store, notifier: WebhookNotifier | None = None):
        self.factory = factory
        self.store = store
        self.notifier = notifier

    def submit(self, who: Principal, instance: Instance, engine: str, time_limit_s: float, seed: int = 0) -> dict:
        if engine == "auto":
            selection = get_selector().choose(instance, time_limit_s).to_dict()
            chosen = selection["engine"]
        else:
            chosen = API_ENGINE[engine]
            selection = {"engine": chosen, "engine_label": ENGINE_LABELS[chosen], "method": "requested",
                         "explanation": f"Engine {ENGINE_LABELS[chosen]} was requested explicitly."}
        algorithm, base = ENGINE_CONFIGS[chosen]
        cfg = {**base, "time_limit_s": time_limit_s}
        if algorithm != "ortools":
            cfg["seed"] = seed
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        with tenant_session(self.factory, who.tenant_id) as s:
            s.add(Plan(id=plan_id, tenant_id=who.tenant_id, instance=instance.to_dict(), requested_engine=engine,
                       engine=chosen, time_limit_s=time_limit_s, selection=_clean(selection), state="queued"))
            audit(s, who.tenant_id, who.key_id, "plan.create", plan_id, engine=chosen, requested=engine)
            s.commit()
        self.store.executor.submit(self._execute, who.tenant_id, plan_id, instance, algorithm, cfg)
        return {"plan_id": plan_id, "state": "queued", "engine": chosen, "selection": selection}

    def _execute(self, tenant_id: str, plan_id: str, instance: Instance, algorithm: str, cfg: dict) -> None:
        with tenant_session(self.factory, tenant_id) as s:
            s.get(Plan, plan_id).state = "running"
            s.commit()
        update: dict[str, Any]
        try:
            rec = self.store.guard.run(instance, algorithm, cfg)
            rec.result.run_id = plan_id
            update = {"state": "completed", "error": None, "result": _clean({
                "solve": rec.result.to_dict(),
                "validation": rec.validation.to_dict() if rec.validation else None,
                "metrics": rec.metrics.to_dict() if rec.metrics else None, "config": cfg})}
        except Exception as exc:  # reported, never hidden
            update = {"state": "failed", "error": f"{type(exc).__name__}: {exc}", "result": None}
        with tenant_session(self.factory, tenant_id) as s:
            plan = s.get(Plan, plan_id)
            for k, v in update.items():
                setattr(plan, k, v)
            plan.finished_at = utcnow()
            status = (update["result"] or {}).get("solve", {}).get("status")
            audit(s, tenant_id, "system", f"plan.{update['state']}", plan_id, status=status)
            s.commit()
        if self.notifier is not None:
            validation = (update["result"] or {}).get("validation") or {}
            self.notifier.emit(tenant_id, f"plan.{update['state']}", plan_id,
                               {"plan_id": plan_id, "state": update["state"], "status": status,
                                "feasible": validation.get("feasible") if update["result"] else None,
                                "engine": cfg_engine(algorithm), "error": update["error"]})

    # ---- P7 replanning ---------------------------------------------------------
    def replan(self, who: Principal, plan_id: str, event, engine: str = "ortools", time_limit_s: float = 5.0,
               warm_start: bool = True, seed: int = 0) -> dict | None:
        """Queue a replan of a completed, feasible plan after a disruption. None = no such plan (for this tenant).
        The clock for disruption_to_feasible_s starts when this request is received."""
        received = time.perf_counter()
        received_at = utcnow()
        with tenant_session(self.factory, who.tenant_id) as s:
            parent = s.get(Plan, plan_id)
            if parent is None:
                return None
            result = parent.result or {}
            ok = result.get("feasible", (result.get("validation") or {}).get("feasible"))
            if parent.state != "completed" or not ok:
                raise PlanStateError(f"plan {plan_id} is {parent.state} and not a feasible plan; "
                                     "only a completed, feasible plan can be replanned")
            routes = result.get("routes") or result["solve"]["routes"]
            parent_instance = Instance.from_dict(parent.instance)
        setup = apply_event(parent_instance, routes, event)  # ReplanError -> 422
        job = build_job(setup, engine, time_limit_s, warm_start, seed)
        new_id = f"plan-{uuid.uuid4().hex[:12]}"
        record = {"parent_plan_id": plan_id, "frozen": setup.frozen, "blocked": setup.blocked,
                  "dropped_customers": setup.dropped, "notes": setup.notes, "warm_start": job.warm_start,
                  "received_at": received_at.isoformat()}
        with tenant_session(self.factory, who.tenant_id) as s:
            s.add(Plan(id=new_id, tenant_id=who.tenant_id, instance=setup.instance.to_dict(), requested_engine=engine,
                       engine=engine, time_limit_s=time_limit_s, state="queued", parent_id=plan_id,
                       event=_clean(event.model_dump()), replan=_clean(record),
                       selection={"engine": engine, "method": "requested",
                                  "explanation": f"Replan with {engine} after a {event.type} event."}))
            audit(s, who.tenant_id, who.key_id, "plan.replan", new_id, parent=plan_id, event=event.type,
                  engine=engine)
            s.commit()
        self.store.executor.submit(self._execute_replan, who.tenant_id, new_id, setup, job, received)
        return {"plan_id": new_id, "parent_plan_id": plan_id, "state": "queued", "engine": engine, "replan": record}

    def _execute_replan(self, tenant_id: str, plan_id: str, setup, job, received: float) -> None:
        with tenant_session(self.factory, tenant_id) as s:
            s.get(Plan, plan_id).state = "running"
            s.commit()
        timing: dict[str, Any] = {}
        feasible = False
        try:
            rec = self.store.guard.run(job.instance, job.algorithm, job.config)
            rec.result.run_id = plan_id
            hidden = ("initial_routes", "initial_tours", "frozen")
            result: dict[str, Any] = {"solve": rec.result.to_dict(),
                                      "config": {k: v for k, v in job.config.items() if k not in hidden}}
            if rec.result.routes is not None:
                routes = routes_by_vehicle(job, rec.result.routes, setup.instance.vehicle_count)
                validation = validate_routes(setup.instance, routes)  # the real instance, not the solver's copy
                problems = check_replan(routes, setup)
                feasible = validation.feasible and not problems
                result.update(routes=routes, validation=validation.to_dict(), replan_violations=problems,
                              feasible=feasible,
                              metrics=compute_metrics(setup.instance, routes, validation).to_dict())
            else:
                result.update(routes=None, validation=None, replan_violations=[], feasible=False, metrics=None)
            done = time.perf_counter()
            diag = rec.result.diagnostics or {}
            timing = {"solver_seconds": rec.result.runtime_seconds, "first_solution_s": diag.get("first_solution_s"),
                      "warm_start_result": diag.get("warm_start"),
                      "disruption_to_result_s": round(done - received, 4),
                      "disruption_to_feasible_s": round(done - received, 4) if feasible else None}
            update = {"state": "completed", "error": None, "result": _clean(result)}
        except Exception as exc:  # reported, never hidden
            update = {"state": "failed", "error": f"{type(exc).__name__}: {exc}", "result": None}
        with tenant_session(self.factory, tenant_id) as s:
            plan = s.get(Plan, plan_id)
            for k, v in update.items():
                setattr(plan, k, v)
            plan.replan = _clean({**(plan.replan or {}), "timing": timing})
            plan.finished_at = utcnow()
            status = ((update["result"] or {}).get("solve") or {}).get("status")
            action = "plan.replanned" if update["state"] == "completed" else "plan.failed"
            audit(s, tenant_id, "system", action, plan_id, status=status, feasible=feasible)
            s.commit()
        if self.notifier is not None:
            self.notifier.emit(tenant_id, action, plan_id,
                               {"plan_id": plan_id, "state": update["state"], "status": status, "feasible": feasible,
                                "engine": job.algorithm, "error": update["error"],
                                "disruption_to_feasible_s": timing.get("disruption_to_feasible_s")})

    def list(self, who: Principal, limit: int = 100) -> list[dict]:
        with tenant_session(self.factory, who.tenant_id) as s:
            rows = s.scalars(select(Plan).order_by(Plan.created_at.desc()).limit(limit))
            out = []
            for p in rows:
                result = p.result or {}
                validation = result.get("validation") or {}
                out.append({
                    "plan_id": p.id, "name": p.instance.get("name", ""), "state": p.state, "engine": p.engine,
                    "requested_engine": p.requested_engine, "n_customers": len(p.instance.get("customers", [])),
                    "status": (result.get("solve") or {}).get("status"),
                    "feasible": result.get("feasible", validation.get("feasible")) if p.result else None,
                    "total_distance": (result.get("metrics") or {}).get("total_distance"),
                    "parent_plan_id": p.parent_id, "event_type": (p.event or {}).get("type"),
                    "created_at": p.created_at.isoformat() if p.created_at else None})
            return out

    def get(self, who: Principal, plan_id: str) -> dict | None:
        with tenant_session(self.factory, who.tenant_id) as s:
            p = s.get(Plan, plan_id)
            if p is None:
                return None
            validation = (p.result or {}).get("validation") or {}
            return {"plan_id": p.id, "state": p.state, "requested_engine": p.requested_engine, "engine": p.engine,
                    "time_limit_s": p.time_limit_s, "selection": p.selection,
                    "status": ((p.result or {}).get("solve") or {}).get("status"),
                    "feasible": p.result.get("feasible", validation.get("feasible")) if p.result else None,
                    "result": p.result, "error": p.error, "instance_id": p.instance.get("instance_id"),
                    "instance": p.instance,
                    "parent_plan_id": p.parent_id, "event": p.event, "replan": p.replan,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "finished_at": p.finished_at.isoformat() if p.finished_at else None}
