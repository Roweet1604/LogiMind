"""Replies built only from tool outputs (templates, no free LLM text), plus a grounding check.

Every number in a reply is copied from a tool output; `ungrounded_numbers` verifies this and the agent
refuses to send a reply that fails it (tests also check it).
"""
from __future__ import annotations

import re
from typing import Any

STATUS = {"solved": "the solver returned a plan", "no_solution": "the solver found no plan",
          "timeout_no_solution": "the time limit ran out before any plan was found",
          "hard_timeout": "the run overran its time limit and was stopped (no plan)",
          "invalid_input": "the input was rejected", "error": "the solver failed"}
ENGINE = {"ortools": "OR-Tools", "ga_ls": "the GA with local search", "ga": "the GA with local search",
          "hybrid": "the hybrid (OR-Tools seed + GA)"}


def _d(v: Any) -> str:
    return "—" if v is None else f"{v:.2f}"


def _verdict(s: dict) -> str:
    if s["state"] in ("queued", "running"):
        return f"Plan {s['plan_id']} is still {s['state']}; it has no result yet."
    if s["state"] == "failed":
        return f"Plan {s['plan_id']} failed: {s.get('error')}."
    status = STATUS.get(s.get("status"), s.get("status") or "no status")
    if s.get("feasible") is True:
        return (f"Plan {s['plan_id']} ({ENGINE.get(s['engine'], s['engine'])}): {status}, and the validator "
                f"accepted it: total distance {_d(s['total_distance'])} with {s['vehicles_used']} vehicles.")
    reasons = "; ".join(s.get("violations") or []) or "no routes"
    return f"Plan {s['plan_id']} ({ENGINE.get(s['engine'], s['engine'])}): {status}. It is NOT feasible ({reasons})."


def render(tool: str, out: dict) -> str:
    if tool in ("solve_with_ortools", "solve_with_ga", "run_hybrid"):
        return f"New plan from the orders of {out['source_plan_id']}. " + _verdict(out)
    if tool == "validate_routes":
        if not out["has_routes"]:
            return f"Plan {out['plan_id']} has no routes to check (state {out['state']}, status {out['status']})."
        if out["feasible"]:
            return f"The validator (version {out['validator_version']}) accepts plan {out['plan_id']}: no violations."
        return (f"The validator (version {out['validator_version']}) rejects plan {out['plan_id']}: "
                f"{out['violation_count']} violations, e.g. " + "; ".join(out["violations"][:3]) + ".")
    if tool == "compare_results":
        lines = [f"{r['plan_id']} ({ENGINE.get(r['engine'], r['engine'])}, {r['time_limit_s']} s): "
                 + ("feasible, distance " + _d(r["total_distance"]) if r["feasible"] else "not feasible")
                 for r in out["plans"]]
        text = "Measured results: " + " | ".join(lines) + "."
        if out["shortest_feasible_plan_id"]:
            text += f" Shortest feasible plan: {out['shortest_feasible_plan_id']}."
        if out["notes"]:
            text += " Caution: " + "; ".join(out["notes"]) + "."
        return text
    if tool == "explain":
        text = _verdict(out)
        if out.get("selection"):
            text += f" Engine choice: {out['selection']}"
        if out.get("event_type"):
            text += f" It replans {out['parent_plan_id']} after a {out['event_type'].replace('_', ' ')}."
        if out.get("replan_notes"):
            text += " Notes: " + "; ".join(out["replan_notes"]) + "."
        return text
    if tool == "reroute":
        text = "Replanned. " + _verdict(out)
        if out.get("disruption_to_feasible_s") is not None:
            text += f" Time from the request to a validated plan: {out['disruption_to_feasible_s']:.2f} s."
        if out.get("replan_notes"):
            text += " Notes: " + "; ".join(out["replan_notes"]) + "."
        return text
    raise ValueError(f"no template for tool {tool!r}")


_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_ID = re.compile(r"\b(?:plan|inst|key|ten|run|wh)-[0-9a-z]+\b")


def _numbers(obj: Any, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        out.extend(float(x) for x in _NUM.findall(_ID.sub(" ", obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers(v, out)


def ungrounded_numbers(text: str, sources: list[Any], extra: tuple[float, ...] = ()) -> list[str]:
    """Numbers in `text` that do not appear (to the shown precision) in any source. Ids are ignored."""
    known: list[float] = []
    _numbers(sources, known)
    bad = []
    for tok in _NUM.findall(_ID.sub(" ", text)):
        val = float(tok)
        tol = 0.5 * 10 ** -(len(tok.split(".")[1]) if "." in tok else 0) + 1e-9
        if not any(abs(val - k) <= tol for k in known) and val not in extra:
            bad.append(tok)
    return bad
