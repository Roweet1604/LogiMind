"""The only things the LLM may output: one Intent, as JSON, validated with Pydantic.

There is deliberately no field for routes, stop sequences or vehicle assignments anywhere in these
schemas, so the LLM cannot hand the system a plan. Plans come only from the solver tools.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.replan.events import Event

PlanId = Annotated[str, Field(pattern=r"^plan-[0-9a-f]{12}$",
                              description="an existing plan id, e.g. plan-0123456789ab")]
Budget = Annotated[float, Field(gt=0, le=60, description="total time budget in seconds")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Solve(_Strict):
    """Re-solve the orders of an existing plan with one engine (creates a NEW plan; the old one is unchanged)."""
    action: Literal["solve"]
    plan_id: PlanId
    engine: Literal["ortools", "ga", "hybrid"]
    time_limit_s: Budget = 5.0


class Validate(_Strict):
    """Run the independent validator again on an existing plan's stored routes."""
    action: Literal["validate"]
    plan_id: PlanId


class Compare(_Strict):
    """Compare the measured results of 2 to 4 existing plans."""
    action: Literal["compare"]
    plan_ids: list[PlanId] = Field(min_length=2, max_length=4)


class Explain(_Strict):
    """Explain an existing plan using only its stored tool outputs (status, validator verdict, metrics)."""
    action: Literal["explain"]
    plan_id: PlanId


class Reroute(_Strict):
    """Replan an active plan after a disruption. Changes the active plan, so it needs the user's confirmation."""
    action: Literal["reroute"]
    plan_id: PlanId
    event: Event
    engine: Literal["ortools", "ga"] = "ortools"
    time_limit_s: Budget = 5.0


class Clarify(_Strict):
    """The request is ambiguous or misses something required; ask one short question."""
    action: Literal["clarify"]
    question: str = Field(min_length=3, max_length=300)


class Refuse(_Strict):
    """The request is outside what the copilot can do (e.g. editing routes by hand, other topics)."""
    action: Literal["refuse"]
    reason: str = Field(min_length=3, max_length=300)


Intent = Annotated[Solve | Validate | Compare | Explain | Reroute | Clarify | Refuse, Field(discriminator="action")]


class IntentEnvelope(_Strict):
    """What the LLM returns: exactly one intent."""
    intent: Intent


ACTIONS = ("solve", "validate", "compare", "explain", "reroute", "clarify", "refuse")
TOOL_FOR = {("solve", "ortools"): "solve_with_ortools", ("solve", "ga"): "solve_with_ga",
            ("solve", "hybrid"): "run_hybrid", ("validate", None): "validate_routes",
            ("compare", None): "compare_results", ("reroute", None): "reroute"}
