"""P8 copilot with the deterministic FakeLLM: intents, the six tools, retry, clarify, refuse, confirmation,
grounding, the no-model case and tenant isolation. No real model is ever called."""
import pytest
from app.copilot.explain import ungrounded_numbers
from app.copilot.llm import FakeLLM, NoLLM, OllamaLLM
from app.copilot.schemas import IntentEnvelope
from app.db.keys import create_tenant, issue_key
from app.db.session import admin_session
from app.main import create_app
from fastapi.testclient import TestClient

from tests.test_plans_api import wait_plan
from tests.test_replan import CVRP, body_of


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path)
    fake = FakeLLM()
    app.state.copilot.llm = fake
    with TestClient(app) as c:
        with admin_session(app.state.db) as s:
            a, b = create_tenant(s, "A"), create_tenant(s, "B")
            _, ka = issue_key(s, a.id)
            _, kb = issue_key(s, b.id)
            s.commit()
        ha, hb = {"X-API-Key": ka}, {"X-API-Key": kb}
        pid = c.post("/api/plans", json={"instance": body_of(CVRP), "engine": "ortools", "time_limit_s": 0.5},
                     headers=ha).json()["plan_id"]
        assert wait_plan(c, pid, ha)["feasible"] is True
        yield c, app, fake, ha, hb, pid


def chat(c, h, message, session_id=None):
    r = c.post("/api/copilot/chat", json={"message": message, "session_id": session_id}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def n_plans(c, h):
    return len(c.get("/api/plans", headers=h).json())


def assert_grounded(reply):
    outputs = [t.get("output") for t in reply["tool_calls"]]
    assert ungrounded_numbers(reply["text"], outputs) == [], reply["text"]


@pytest.mark.parametrize("engine,tool,algo", [("ortools", "solve_with_ortools", "ortools"),
                                              ("ga", "solve_with_ga", "ga_ls"), ("hybrid", "run_hybrid", "hybrid")])
def test_solve_tools_make_a_new_validated_plan_and_the_reply_uses_tool_numbers(env, engine, tool, algo):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "solve", "plan_id": pid, "engine": engine, "time_limit_s": 0.5}}]
    before = n_plans(c, ha)
    r = chat(c, ha, f"re-run the latest plan with {engine}")
    assert r["kind"] == "answer" and r["tool_calls"][0]["tool"] == tool
    out = r["tool_calls"][0]["output"]
    assert out["feasible"] is True and out["engine"] == algo and out["source_plan_id"] == pid
    assert f"{out['total_distance']:.2f}" in r["text"] and "validator accepted" in r["text"]
    assert_grounded(r)
    assert n_plans(c, ha) == before + 1
    assert pid in fake.calls[0]["system"]  # the tenant's plans are given as context


def test_validate_compare_and_explain(env):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "solve", "plan_id": pid, "engine": "ortools", "time_limit_s": 0.5}}]
    other = chat(c, ha, "solve again")["tool_calls"][0]["output"]["plan_id"]
    fake.script = [{"intent": {"action": "validate", "plan_id": pid}}]
    r = chat(c, ha, "is it valid?")
    assert r["tool_calls"][0]["tool"] == "validate_routes" and r["tool_calls"][0]["output"]["feasible"] is True
    assert "accepts" in r["text"]
    assert_grounded(r)
    fake.script = [{"intent": {"action": "compare", "plan_ids": [pid, other]}}]
    r = chat(c, ha, "compare them")
    out = r["tool_calls"][0]["output"]
    assert r["tool_calls"][0]["tool"] == "compare_results" and out["same_instance"] is True
    assert out["shortest_feasible_plan_id"] in (pid, other)
    assert_grounded(r)
    fake.script = [{"intent": {"action": "explain", "plan_id": pid}}]
    r = chat(c, ha, "why?")
    assert r["kind"] == "answer" and "requested explicitly" in r["text"]
    assert_grounded(r)


def test_compare_warns_when_budgets_differ(env):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "solve", "plan_id": pid, "engine": "ortools", "time_limit_s": 1}}]
    other = chat(c, ha, "solve with 1 s")["tool_calls"][0]["output"]["plan_id"]
    fake.script = [{"intent": {"action": "compare", "plan_ids": [pid, other]}}]
    r = chat(c, ha, "compare")
    assert "not an equal-clock comparison" in r["text"]


def test_invalid_output_is_retried_once_with_the_error(env):
    c, app, fake, ha, hb, pid = env
    fake.script = ["not json at all", {"intent": {"action": "validate", "plan_id": pid}}]
    r = chat(c, ha, "check plan")
    assert r["kind"] == "answer" and r["parse_attempts"] == 2
    assert "invalid" in fake.calls[1]["messages"][-1]["content"]


def test_two_invalid_outputs_end_in_a_clarifying_question(env):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "fly"}}, "{}"]
    r = chat(c, ha, "do the thing")
    assert r["kind"] == "clarify" and r["parse_attempts"] == 2 and r["tool_calls"] == []
    assert len(fake.calls) == 2  # exactly one retry


def test_llm_cannot_supply_routes(env):
    c, app, fake, ha, hb, pid = env
    with_routes = {"intent": {"action": "solve", "plan_id": pid, "engine": "ortools", "routes": [[1, 2, 3]]}}
    fake.script = [with_routes, with_routes]
    before = n_plans(c, ha)
    r = chat(c, ha, "use these routes: 1 2 3")
    assert r["kind"] == "clarify" and n_plans(c, ha) == before
    fields: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            fields.update(node.get("properties", {}))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(IntentEnvelope.model_json_schema())
    assert fields and not any("route" in f or "stop" in f or "sequence" in f for f in fields), fields


def test_clarify_and_refuse_intents(env):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "clarify", "question": "Which vehicle broke down?"}}]
    assert chat(c, ha, "a truck broke")["kind"] == "clarify"
    fake.script = [{"intent": {"action": "refuse", "reason": "editing stop orders by hand is not supported"}}]
    r = chat(c, ha, "move customer 5 to truck 2")
    assert r["kind"] == "refuse" and "not supported" in r["text"] and r["tool_calls"] == []


def test_unknown_plan_gives_a_clarifying_question(env):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "validate", "plan_id": "plan-000000000000"}}]
    r = chat(c, ha, "validate plan 0")
    assert r["kind"] == "clarify" and pid in r["text"]


def test_reroute_needs_confirmation_before_the_active_plan_changes(env):
    c, app, fake, ha, hb, pid = env
    plan = c.get(f"/api/plans/{pid}", headers=ha).json()
    v = next(i for i, r in enumerate(plan["result"]["solve"]["routes"]) if r)
    reroute = {"intent": {"action": "reroute", "plan_id": pid, "time_limit_s": 0.5,
                          "event": {"type": "vehicle_breakdown", "vehicle": v, "completed": {str(v): 1}}}}
    fake.script = [reroute]
    before = n_plans(c, ha)
    r = chat(c, ha, f"truck {v} broke down after its first stop")
    assert r["kind"] == "confirm" and r["pending_id"] and n_plans(c, ha) == before  # nothing changed yet
    sid = r["session_id"]
    bad = c.post("/api/copilot/confirm", json={"session_id": sid, "pending_id": "pend-nope", "approve": True},
                 headers=ha)
    assert bad.json()["kind"] == "error" and n_plans(c, ha) == before
    ok = c.post("/api/copilot/confirm", json={"session_id": sid, "pending_id": r["pending_id"], "approve": True},
                headers=ha).json()
    assert ok["kind"] == "answer" and ok["tool_calls"][0]["tool"] == "reroute"
    out = ok["tool_calls"][0]["output"]
    assert out["feasible"] is True and out["parent_plan_id"] == pid and out["disruption_to_feasible_s"] > 0
    assert_grounded(ok)
    assert n_plans(c, ha) == before + 1
    again = c.post("/api/copilot/confirm", json={"session_id": sid, "pending_id": r["pending_id"], "approve": True},
                   headers=ha).json()
    assert again["kind"] == "error"  # a confirmation is used once


def test_cancel_and_new_message_drop_the_pending_change(env):
    c, app, fake, ha, hb, pid = env
    reroute = {"intent": {"action": "reroute", "plan_id": pid, "event": {"type": "urgent_order",
               "customer": {"id": 999, "x": 50, "y": 50, "demand": 1}}}}
    fake.script = [reroute]
    r = chat(c, ha, "add an urgent order")
    cancel = c.post("/api/copilot/confirm", json={"session_id": r["session_id"], "pending_id": r["pending_id"],
                                                  "approve": False}, headers=ha).json()
    assert "not changed" in cancel["text"]
    fake.script = [reroute, {"intent": {"action": "explain", "plan_id": pid}}]
    r = chat(c, ha, "add an urgent order")
    chat(c, ha, "actually, explain it", session_id=r["session_id"])
    late = c.post("/api/copilot/confirm", json={"session_id": r["session_id"], "pending_id": r["pending_id"],
                                                "approve": True}, headers=ha).json()
    assert late["kind"] == "error"


def test_copilot_is_tenant_isolated(env):
    c, app, fake, ha, hb, pid = env
    fake.script = [{"intent": {"action": "explain", "plan_id": pid}}]
    r = chat(c, hb, f"explain {pid}")
    assert r["kind"] == "clarify" and "can't find" in r["text"]  # B cannot reach A's plan
    assert pid not in fake.calls[-1]["system"]  # and A's plans are not in B's context
    reroute = {"intent": {"action": "reroute", "plan_id": pid, "event": {"type": "vehicle_breakdown", "vehicle": 0}}}
    fake.script = [reroute]
    pending = chat(c, ha, "breakdown")
    stolen = c.post("/api/copilot/confirm", json={"session_id": pending["session_id"],
                                                  "pending_id": pending["pending_id"], "approve": True},
                    headers=hb).json()
    assert stolen["kind"] == "error" and n_plans(c, hb) == 0
    assert c.post("/api/copilot/chat", json={"message": "hi"}).status_code == 401


def test_no_model_is_said_plainly(env, tmp_path):
    c, app, fake, ha, hb, pid = env
    app.state.copilot.llm = NoLLM()
    r = chat(c, ha, "solve")
    assert r["kind"] == "unavailable" and "not available" in r["text"]
    assert c.get("/api/copilot/status", headers=ha).json()["available"] is False
    down = OllamaLLM(url="http://127.0.0.1:9", model="llama3.2:3b").availability()  # nothing listens on port 9
    assert not down.available and "not running" in down.reason and "ollama pull llama3.2:3b" in down.reason


def test_grounding_check_catches_invented_numbers():
    out = {"total_distance": 123.456, "vehicles_used": 3, "plan_id": "plan-0123456789ab"}
    assert ungrounded_numbers("plan-0123456789ab: distance 123.46 with 3 vehicles", [out]) == []
    assert ungrounded_numbers("distance 120.00 with 3 vehicles", [out]) == ["120.00"]
    assert ungrounded_numbers("saves 15% fuel", [out]) == ["15"]
