"""Tenant plans: stored in the database, solved on the store's single solver thread.

Plans share the store's one worker thread and guarded worker process with the
research runs, so solver jobs still run one at a time. Every plan's routes go
through the independent validator; `feasible` is the validator's verdict, and
timeouts or failures are stored as what they are.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.db.keys import Principal
from app.db.models import AuditLog, Plan, utcnow
from app.db.session import tenant_session
from app.models.problem import Instance
from app.selector.dataset import ENGINE_CONFIGS
from app.selector.model import ENGINE_LABELS, get_selector
from app.services.notify import WebhookNotifier
from app.services.store import Store, _clean

API_ENGINE = {"ortools": "ortools", "hybrid": "hybrid", "ga": "ga_ls"}  # the API's "ga" is GA + local search


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

    def get(self, who: Principal, plan_id: str) -> dict | None:
        with tenant_session(self.factory, who.tenant_id) as s:
            p = s.get(Plan, plan_id)
            if p is None:
                return None
            validation = (p.result or {}).get("validation") or {}
            return {"plan_id": p.id, "state": p.state, "requested_engine": p.requested_engine, "engine": p.engine,
                    "time_limit_s": p.time_limit_s, "selection": p.selection,
                    "status": ((p.result or {}).get("solve") or {}).get("status"),
                    "feasible": validation.get("feasible") if p.result else None,
                    "result": p.result, "error": p.error, "instance_id": p.instance.get("instance_id"),
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "finished_at": p.finished_at.isoformat() if p.finished_at else None}
