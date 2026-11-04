"""Copilot tools. Each one calls the platform (solvers through PlanService, the independent validator) for one
tenant and returns plain data. These outputs are the ONLY source of facts for the copilot's replies.

solve_with_ortools / solve_with_ga / run_hybrid: re-solve an existing plan's orders as a NEW plan.
validate_routes: re-run the validator on a plan's stored routes (routes come from the database, never the LLM).
compare_results: measured results of 2-4 plans, with a fairness note.
reroute: replan after a disruption (POST /plans/{id}/replan semantics; needs confirmation, see agent.py).
"""
from __future__ import annotations

import time
from typing import Any

from app.db.keys import Principal
from app.evaluation.validator import validate_routes as run_validator
from app.models.problem import Instance
from app.services.plans import PlanService

TOOL_NAMES = ("solve_with_ortools", "solve_with_ga", "run_hybrid", "validate_routes", "compare_results", "reroute")


class ToolError(ValueError):
    """The tool could not run (e.g. unknown plan). The message is shown to the user as is."""


def _routes(plan: dict) -> list[list[int]] | None:
    result = plan.get("result") or {}
    return result.get("routes") or (result.get("solve") or {}).get("routes")


def summary(plan: dict) -> dict[str, Any]:
    result = plan.get("result") or {}
    metrics = result.get("metrics") or {}
    validation = result.get("validation") or {}
    timing = (plan.get("replan") or {}).get("timing") or {}
    return {
        "plan_id": plan["plan_id"], "state": plan["state"], "engine": plan["engine"], "status": plan.get("status"),
        "feasible": plan.get("feasible"), "total_distance": metrics.get("total_distance"),
        "vehicles_used": metrics.get("vehicles_used"), "unserved_customers": metrics.get("unserved_customers"),
        "violations": [v.get("detail") for v in validation.get("violations", [])][:5]
        + list(result.get("replan_violations") or [])[:5],
        "time_limit_s": plan.get("time_limit_s"), "instance_id": plan.get("instance_id"),
        "n_customers": len((plan.get("instance") or {}).get("customers", [])),
        "error": plan.get("error"), "parent_plan_id": plan.get("parent_plan_id"),
        "disruption_to_feasible_s": timing.get("disruption_to_feasible_s"),
    }


class CopilotTools:
    def __init__(self, plans: PlanService, who: Principal, wait_factor: float = 1.5, wait_grace_s: float = 20.0):
        self.plans, self.who = plans, who
        self.wait_factor, self.wait_grace_s = wait_factor, wait_grace_s

    def _get(self, plan_id: str) -> dict:
        plan = self.plans.get(self.who, plan_id)
        if plan is None:
            raise ToolError(f"plan {plan_id} was not found for your account")
        return plan

    def _wait(self, plan_id: str, budget: float) -> dict:
        end = time.monotonic() + self.wait_factor * budget + self.wait_grace_s
        while True:
            plan = self._get(plan_id)
            if plan["state"] in ("completed", "failed") or time.monotonic() > end:
                return plan  # a still-running plan is reported as running, never as done
            time.sleep(0.1)

    # ---- solvers ----------------------------------------------------------------
    def _solve(self, plan_id: str, engine: str, time_limit_s: float) -> dict:
        base = self._get(plan_id)
        inst = Instance.from_dict(base["instance"])
        queued = self.plans.submit(self.who, inst, engine, time_limit_s)
        out = summary(self._wait(queued["plan_id"], time_limit_s))
        out["source_plan_id"] = plan_id
        return out

    def solve_with_ortools(self, plan_id: str, time_limit_s: float) -> dict:
        return self._solve(plan_id, "ortools", time_limit_s)

    def solve_with_ga(self, plan_id: str, time_limit_s: float) -> dict:
        return self._solve(plan_id, "ga", time_limit_s)

    def run_hybrid(self, plan_id: str, time_limit_s: float) -> dict:
        return self._solve(plan_id, "hybrid", time_limit_s)

    # ---- checks and comparisons -------------------------------------------------
    def validate_routes(self, plan_id: str) -> dict:
        plan = self._get(plan_id)
        routes = _routes(plan)
        if routes is None:
            return {"plan_id": plan_id, "has_routes": False, "state": plan["state"], "status": plan.get("status")}
        v = run_validator(Instance.from_dict(plan["instance"]), routes)
        return {"plan_id": plan_id, "has_routes": True, "feasible": v.feasible,
                "validator_version": v.validator_version,
                "violations": [x.detail for x in v.violations][:10], "violation_count": len(v.violations),
                "unserved": v.unserved, "total_lateness": v.total_lateness}

    def compare_results(self, plan_ids: list[str]) -> dict:
        rows = [summary(self._get(p)) for p in plan_ids]
        same_instance = len({r["instance_id"] for r in rows}) == 1
        same_budget = len({r["time_limit_s"] for r in rows}) == 1
        notes = []
        if not same_instance:
            notes.append("the plans are for different orders, so their distances are not comparable")
        if not same_budget:
            notes.append("the plans had different time budgets, so this is not an equal-clock comparison")
        feasible = [r for r in rows if r["feasible"] is True and r["total_distance"] is not None]
        best = min(feasible, key=lambda r: r["total_distance"])["plan_id"] if feasible and same_instance else None
        return {"plans": rows, "same_instance": same_instance, "same_budget": same_budget,
                "shortest_feasible_plan_id": best, "notes": notes}

    def explain(self, plan_id: str) -> dict:
        plan = self._get(plan_id)
        out = summary(plan)
        out["selection"] = (plan.get("selection") or {}).get("explanation")
        out["replan_notes"] = (plan.get("replan") or {}).get("notes") or []
        out["event_type"] = (plan.get("event") or {}).get("type")
        return out

    # ---- disruption ----------------------------------------------------------------
    def reroute(self, plan_id: str, event: Any, engine: str, time_limit_s: float) -> dict:
        from app.replan.events import ReplanError
        from app.services.plans import PlanStateError
        self._get(plan_id)
        try:
            queued = self.plans.replan(self.who, plan_id, event, engine, time_limit_s)
        except (ReplanError, PlanStateError) as exc:
            raise ToolError(f"the replan was not accepted: {exc}")
        plan = self._wait(queued["plan_id"], time_limit_s)
        out = summary(plan)
        out["replan_notes"] = (plan.get("replan") or {}).get("notes") or []
        out["dropped_customers"] = (plan.get("replan") or {}).get("dropped_customers") or []
        return out
