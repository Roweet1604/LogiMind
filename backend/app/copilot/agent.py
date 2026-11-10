"""The copilot agent (LangGraph).

    parse --(valid intent)--> decide --(clarify/refuse)----------------------> reply
      ^  \\--(invalid, 1st try)--> parse (retry with the error)                 ^
      |   \\--(invalid twice)----> clarify fallback ----------------------------|
      |                     decide --(reroute)--> ask for confirmation ---------|
      |                     decide --(solve/validate/compare/explain)--> tool --> grounded reply

* The LLM only produces an `IntentEnvelope` (schema-constrained JSON, Pydantic-validated, one retry).
* Tools do the work; replies are templates over tool outputs and pass `ungrounded_numbers`.
* Reroute changes an active plan, so it is held as a pending action until the user confirms it.
* Sessions are per tenant and in memory (lost on restart).
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.copilot.explain import render, ungrounded_numbers
from app.copilot.llm import LLM, LLMError, LLMUnavailable
from app.copilot.schemas import TOOL_FOR, IntentEnvelope, Reroute
from app.copilot.tools import CopilotTools, ToolError
from app.db.keys import Principal
from app.services.plans import PlanService

MAX_HISTORY = 10
SYSTEM = """You are the LogiMind dispatch copilot. Turn the user's message into exactly ONE intent, as JSON that
matches the given schema. Do not answer in prose.

Actions:
- solve: re-solve the orders of an existing plan with engine "ortools", "ga" or "hybrid" (makes a new plan).
- validate: re-check an existing plan with the validator.
- compare: compare 2 to 4 existing plans.
- explain: explain an existing plan's result.
- reroute: replan an existing plan after a disruption: event.type is "vehicle_breakdown" (with "vehicle"),
  "failed_delivery" (with "customer_id" and "retry") or "urgent_order" (with "customer": id, x, y, demand).
  event.completed maps vehicle index -> number of stops already done.
- clarify: ask ONE short question when the plan, the engine, the vehicle or another required value is unclear.
- refuse: anything else, e.g. writing or editing routes or stop orders by hand, moving a stop to a vehicle,
  prices, or topics outside route planning. You never write routes.

Rules: use only plan ids from the list below or from the conversation; never invent ids, numbers or results.
If the user says "the latest plan", use the first plan in the list. If unsure, clarify.

The user's plans (newest first):
{plans}
"""


class GraphState(TypedDict, total=False):
    message: str
    history: list[dict[str, str]]
    plans_context: str
    llm: Any  # the LLM for this request (console settings, decision 0033) or the server's default
    attempts: int
    error: str | None
    raw: str | None
    intent: Any
    reply: dict


@dataclass
class Session:
    history: list[dict[str, str]] = field(default_factory=list)
    pending: dict[str, Any] | None = None  # {"id", "intent"}


def _plans_context(plans: PlanService, who: Principal) -> str:
    rows = plans.list(who, 15)
    if not rows:
        return "(no plans yet)"
    return "\n".join(f"- {r['plan_id']}: {r['name'] or 'unnamed'}, engine {r['engine']}, {r['state']}, "
                     f"feasible={r['feasible']}, {r['n_customers']} orders"
                     + (f", replan of {r['parent_plan_id']} ({r['event_type']})" if r["parent_plan_id"] else "")
                     for r in rows)


class Copilot:
    def __init__(self, plans: PlanService, llm: LLM):
        self.plans, self.llm = plans, llm
        self.sessions: dict[tuple[str, str], Session] = {}
        self._lock = threading.Lock()
        self.schema = IntentEnvelope.model_json_schema()
        self.graph = self._build()

    # ---- graph ------------------------------------------------------------------
    def _build(self):
        g = StateGraph(GraphState)
        g.add_node("parse", self._parse)
        g.add_node("fallback", self._fallback)
        g.add_edge(START, "parse")
        g.add_conditional_edges("parse", self._after_parse, {"retry": "parse", "fallback": "fallback", "done": END})
        g.add_edge("fallback", END)
        return g.compile()

    def _parse(self, state: GraphState) -> GraphState:
        attempts = state.get("attempts", 0) + 1
        messages = list(state.get("history", [])) + [{"role": "user", "content": state["message"]}]
        if state.get("error"):
            messages += [{"role": "assistant", "content": state.get("raw") or ""},
                         {"role": "user", "content": f"That output was invalid: {state['error']}. "
                                                     "Return only one JSON object that matches the schema."}]
        system = SYSTEM.format(plans=state["plans_context"])
        raw = (state.get("llm") or self.llm).complete_json(system, messages, self.schema)
        try:
            env = IntentEnvelope.model_validate_json(raw)
        except ValidationError as exc:
            short = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])
            return {"attempts": attempts, "error": short or "not valid JSON", "raw": raw[:2000], "intent": None}
        return {"attempts": attempts, "error": None, "raw": raw, "intent": env.intent}

    @staticmethod
    def _after_parse(state: GraphState) -> str:
        if state.get("intent") is not None:
            return "done"
        return "retry" if state.get("attempts", 0) < 2 else "fallback"

    @staticmethod
    def _fallback(state: GraphState) -> GraphState:
        return {"reply": {"kind": "clarify", "text": "I could not turn that into a request I can run. Could you say "
                          "which plan it is about and what to do (solve, validate, compare, explain or replan)?",
                          "parse_error": state.get("error")}}

    # ---- public API ---------------------------------------------------------------
    def status(self, llm: LLM | None = None) -> dict:
        return (llm or self.llm).availability().to_dict()

    def list_models(self, llm: LLM | None = None) -> dict:
        """The provider's chat models for the console's "Load models" (decision 0035). Never the key."""
        llm = llm or self.llm
        av = {"provider": getattr(llm, "provider", None)}
        try:
            models = llm.list_models()
        except (LLMError, LLMUnavailable) as exc:
            text = str(exc)
            scrub = getattr(llm, "_scrub", None)
            return {**av, "ok": False, "kind": getattr(exc, "kind", "none"), "models": [],
                    "message": scrub(text) if scrub else text}
        if not models:
            return {**av, "ok": False, "kind": "model", "models": [],
                    "message": "The provider answered, but its list has no chat models. Type the model name instead."}
        return {**av, "ok": True, "kind": "ok", "models": models,
                "message": f"{len(models)} chat model{'s' if len(models) != 1 else ''} found. Pick one."}

    def test_connection(self, llm: LLM | None = None) -> dict:
        llm = llm or self.llm
        if hasattr(llm, "test_connection"):
            return llm.test_connection()
        av = llm.availability()
        return {"ok": av.available, "kind": "ok" if av.available else "network", "provider": av.provider,
                "model": av.model, "message": av.reason}

    def _session(self, who: Principal, session_id: str | None) -> tuple[str, Session]:
        sid = session_id or f"chat-{uuid.uuid4().hex[:12]}"
        with self._lock:
            return sid, self.sessions.setdefault((who.tenant_id, sid), Session())

    def chat(self, who: Principal, message: str, session_id: str | None = None, llm: LLM | None = None) -> dict:
        """`llm`: this request's model from the console's settings (never stored); None = the server's own."""
        llm = llm or self.llm
        sid, session = self._session(who, session_id)
        session.pending = None  # a new message cancels an unconfirmed change
        av = llm.availability()
        if not av.available:
            return {"session_id": sid, "kind": "unavailable", "text": f"The copilot is not available: {av.reason}. "
                    "Plans, imports and replans still work from the console.", "llm": av.to_dict(), "tool_calls": []}
        try:
            state = self.graph.invoke({"message": message, "history": session.history[-MAX_HISTORY:],
                                       "plans_context": _plans_context(self.plans, who), "attempts": 0, "llm": llm})
        except LLMUnavailable as exc:
            return {"session_id": sid, "kind": "unavailable", "text": f"The copilot is not available: {exc}.",
                    "tool_calls": []}
        except LLMError as exc:  # hosted provider: rejected key, rate limit, network, server error, as they are
            return {"session_id": sid, "kind": "unavailable" if exc.kind == "auth" else "error", "text": str(exc),
                    "llm_error": exc.kind, "llm": llm.availability().to_dict(), "tool_calls": []}
        reply = state.get("reply") or self._decide(who, session, state["intent"])
        reply.setdefault("tool_calls", [])
        reply["parse_attempts"] = state.get("attempts")
        intent = state.get("intent")
        reply["intent"] = intent.model_dump() if intent is not None else None
        session.history += [{"role": "user", "content": message},
                            {"role": "assistant", "content": json.dumps({"intent": reply["intent"]})}]
        return {"session_id": sid, **reply}

    def confirm(self, who: Principal, session_id: str, pending_id: str, approve: bool) -> dict:
        sid, session = self._session(who, session_id)
        pending = session.pending
        if not pending or pending["id"] != pending_id:
            return {"session_id": sid, "kind": "error", "text": "There is no pending change with that id (it may have "
                    "been replaced by a newer message). Nothing was changed.", "tool_calls": []}
        session.pending = None
        if not approve:
            return {"session_id": sid, "kind": "answer", "text": "Cancelled. The plan was not changed.",
                    "tool_calls": []}
        intent: Reroute = pending["intent"]
        return {"session_id": sid, **self._run(who, "reroute", intent)}

    # ---- decisions and tools ----------------------------------------------------------
    def _decide(self, who: Principal, session: Session, intent: Any) -> dict:
        if intent.action == "clarify":
            return {"kind": "clarify", "text": intent.question}
        if intent.action == "refuse":
            return {"kind": "refuse", "text": f"I can't do that: {intent.reason}. I can solve, validate, compare or "
                    "explain plans, and replan after a breakdown, failed delivery or urgent order."}
        if intent.action == "reroute":
            if self.plans.get(who, intent.plan_id) is None:
                return self._unknown_plan(who, intent.plan_id)
            pid = f"pend-{uuid.uuid4().hex[:8]}"
            session.pending = {"id": pid, "intent": intent}
            e = intent.event
            what = {"vehicle_breakdown": f"vehicle {getattr(e, 'vehicle', '?')} broke down",
                    "failed_delivery": f"the delivery to customer {getattr(e, 'customer_id', '?')} failed",
                    "urgent_order": f"urgent order {getattr(getattr(e, 'customer', None), 'id', '?')} arrived"}[e.type]
            return {"kind": "confirm", "pending_id": pid,
                    "text": f"This replans active plan {intent.plan_id} because {what}, with {intent.engine} and a "
                            f"{intent.time_limit_s:g} s budget. Completed stops: {e.completed or 'none'}. Confirm?"}
        tool = TOOL_FOR.get((intent.action, getattr(intent, "engine", None))) or TOOL_FOR.get((intent.action, None)) \
            or "explain"
        return self._run(who, tool, intent)

    def _unknown_plan(self, who: Principal, plan_id: str) -> dict:
        recent = [r["plan_id"] for r in self.plans.list(who, 5)]
        return {"kind": "clarify", "text": f"I can't find plan {plan_id} in your account. Which plan do you mean? "
                f"Recent plans: {', '.join(recent) or 'none yet'}."}

    def _run(self, who: Principal, tool: str, intent: Any) -> dict:
        tools = CopilotTools(self.plans, who)
        if tool == "compare_results":
            args = {"plan_ids": intent.plan_ids}
        elif tool == "reroute":
            args = {"plan_id": intent.plan_id, "event": intent.event, "engine": intent.engine,
                    "time_limit_s": intent.time_limit_s}
        elif tool in ("validate_routes", "explain"):
            args = {"plan_id": intent.plan_id}
        else:
            args = {"plan_id": intent.plan_id, "time_limit_s": intent.time_limit_s}
        try:
            out = getattr(tools, tool)(**args)
        except ToolError as exc:
            if "not found" in str(exc):
                return self._unknown_plan(who, getattr(intent, "plan_id", None) or ", ".join(intent.plan_ids))
            return {"kind": "error", "text": str(exc),
                    "tool_calls": [{"tool": tool, "args": _jsonable(args), "error": str(exc)}]}
        text = render(tool, out)
        bad = ungrounded_numbers(text, [out])
        if bad:  # never send a number that no tool produced
            return {"kind": "error", "text": "Internal check failed: the reply contained numbers not found in the "
                    f"tool output ({', '.join(bad)}); it was not sent.", "tool_calls": []}
        return {"kind": "answer", "text": text, "tool_calls": [{"tool": tool, "args": _jsonable(args), "output": out}]}


def _jsonable(args: dict) -> dict:
    return {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in args.items()}
