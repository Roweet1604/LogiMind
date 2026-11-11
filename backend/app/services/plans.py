"""Tenant plans: stored in the database and solved by a worker through the durable job queue.

`submit` and `replan` store the plan AND its job in one transaction; a worker process (app/jobs/worker.py)
claims the job, runs it in the guarded solver process and writes the result (app/jobs/execute.py). Every
plan's routes go through the independent validator; `feasible` is the validator's verdict, and timeouts or
failures are stored as what they are.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.keys import Principal
from app.db.models import AuditLog, Plan, utcnow
from app.db.session import tenant_session
from app.distances.service import DistanceService, describe
from app.jobs.queue import JobQueue
from app.models.problem import Instance
from app.replan.events import apply_event, extra_points
from app.replan.jobs import build_job, setup_payload
from app.selector.dataset import ENGINE_CONFIGS
from app.selector.model import ENGINE_LABELS, get_selector
from app.services.store import _clean

API_ENGINE = {"ortools": "ortools", "hybrid": "hybrid", "ga": "ga_ls"}  # the API's "ga" is GA + local search


class PlanStateError(ValueError):
    """The plan exists but cannot be replanned (not finished, or not feasible)."""


def cfg_engine(algorithm: str) -> str:
    return {"ga": "ga_ls"}.get(algorithm, algorithm)


def audit(s: Session, tenant_id: str, actor: str, action: str, target: str = "", **detail: Any) -> None:
    s.add(AuditLog(tenant_id=tenant_id, actor=actor, action=action, target=target, detail=_clean(detail) or None))


class PlanService:
    def __init__(self, factory: sessionmaker[Session], queue: JobQueue, distances: DistanceService | None = None):
        self.factory = factory
        self.queue = queue
        self.distances = distances

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
        stored = instance.to_dict()
        source = describe(stored)
        with tenant_session(self.factory, who.tenant_id) as s:
            s.add(Plan(id=plan_id, tenant_id=who.tenant_id, instance=stored, requested_engine=engine,
                       engine=chosen, time_limit_s=time_limit_s, selection=_clean(selection), state="queued"))
            s.flush()  # the plan row first: the job refers to it
            job_id = self.queue.enqueue(s, "plan", {"algorithm": algorithm, "config": cfg}, who.tenant_id, plan_id)
            audit(s, who.tenant_id, who.key_id, "plan.create", plan_id, engine=chosen, requested=engine,
                  distances=source["provider"], distance_fallback=source["fallback"], job_id=job_id)
            s.commit()
        self.queue.notify()
        return {"plan_id": plan_id, "state": "queued", "engine": chosen, "selection": selection,
                "distance_source": source}

    # ---- P7 replanning ---------------------------------------------------------
    def replan(self, who: Principal, plan_id: str, event, engine: str = "ortools", time_limit_s: float = 5.0,
               warm_start: bool = True, seed: int = 0) -> dict | None:
        """Queue a replan of a completed, feasible plan after a disruption. None = no such plan (for this tenant).
        The clock for disruption_to_feasible_s starts when this request is received (wall clock: the worker
        that finishes the job is another process)."""
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
            earlier = dict(parent.replan or {})
        parent_road_ok = parent_instance.road is not None and not parent_instance.road.fallback
        if parent_instance.road is not None and self.distances is not None:
            # an urgent order's stop needs matrix rows: rebuild from the same requested source (fallback flagged)
            parent_instance = self.distances.cover(parent_instance, extra=extra_points(event))
        setup = apply_event(parent_instance, routes, event, earlier)  # ReplanError -> 422
        job = build_job(setup, engine, time_limit_s, warm_start, seed)  # ReplanError (e.g. GA + frozen) -> 422
        new_id = f"plan-{uuid.uuid4().hex[:12]}"
        stored = setup.instance.to_dict()
        source = describe(stored)
        if source.get("fallback") and parent_road_ok:
            setup.notes.append("distances changed: OSRM was not available for the new stop, so this replan uses "
                               "the straight-line fallback for the whole matrix")
        record = {"parent_plan_id": plan_id, "frozen": setup.frozen, "blocked": setup.blocked,
                  "dropped_customers": setup.dropped, "retry": setup.retry, "notes": setup.notes,
                  "warm_start": job.warm_start,
                  "received_at": received_at.isoformat()}
        with tenant_session(self.factory, who.tenant_id) as s:
            s.add(Plan(id=new_id, tenant_id=who.tenant_id, instance=stored, requested_engine=engine,
                       engine=engine, time_limit_s=time_limit_s, state="queued", parent_id=plan_id,
                       event=_clean(event.model_dump()), replan=_clean(record),
                       selection={"engine": engine, "method": "requested",
                                  "explanation": f"Replan with {engine} after the event {event.type}."}))
            s.flush()
            job_id = self.queue.enqueue(s, "replan", {
                "setup": setup_payload(setup, event.now), "engine": engine, "time_limit_s": time_limit_s,
                "warm_start": warm_start, "seed": seed}, who.tenant_id, new_id)
            audit(s, who.tenant_id, who.key_id, "plan.replan", new_id, parent=plan_id, event=event.type,
                  engine=engine, job_id=job_id)
            s.commit()
        self.queue.notify()
        return {"plan_id": new_id, "parent_plan_id": plan_id, "state": "queued", "engine": engine, "replan": record,
                "distance_source": source}

    def list(self, who: Principal, limit: int = 100) -> list[dict]:
        with tenant_session(self.factory, who.tenant_id) as s:
            rows = s.scalars(select(Plan).order_by(Plan.created_at.desc()).limit(limit))
            out = []
            for p in rows:
                result = p.result or {}
                validation = result.get("validation") or {}
                source = describe(p.instance)
                out.append({
                    "plan_id": p.id, "name": p.instance.get("name", ""), "state": p.state, "engine": p.engine,
                    "requested_engine": p.requested_engine, "n_customers": len(p.instance.get("customers", [])),
                    "status": (result.get("solve") or {}).get("status"),
                    "feasible": result.get("feasible", validation.get("feasible")) if p.result else None,
                    "total_distance": (result.get("metrics") or {}).get("total_distance"),
                    "distance_provider": source["provider"], "distance_fallback": source["fallback"],
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
                    "instance": p.instance, "distance_source": describe(p.instance),
                    "job": job.public() if (job := self.queue.for_plan(p.id, who.tenant_id)) else None,
                    "parent_plan_id": p.parent_id, "event": p.event, "replan": p.replan,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "finished_at": p.finished_at.isoformat() if p.finished_at else None}
