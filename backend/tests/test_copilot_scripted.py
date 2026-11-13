"""Scripted demo stand-in (LOGIMIND_LLM_PROVIDER=scripted, decision 0042): fixed rules, never a language model.
Its intents pass the same schema, and a replan still waits for the user's confirmation."""
from pathlib import Path

from app.copilot.llm import ScriptedLLM, llm_from_env
from app.copilot.schemas import IntentEnvelope

from tests.test_copilot import env  # noqa: F401  (fixture: app, two tenants, one feasible plan)

SYSTEM = "The user's plans (newest first):\n- plan-0123456789ab: b, engine ortools\n- plan-ba9876543210: a, engine ga\n"


def intent(text: str) -> dict:
    raw = ScriptedLLM().complete_json(SYSTEM, [{"role": "user", "content": text}], {})
    return IntentEnvelope.model_validate_json(raw).intent.model_dump(mode="json", exclude_none=True)


def test_selected_by_env_and_labelled_as_scripted():
    llm = llm_from_env({"LOGIMIND_LLM_PROVIDER": "scripted"}, Path("missing.env"))
    assert isinstance(llm, ScriptedLLM)
    a = llm.availability()
    assert a.available and (a.provider, a.model) == ("scripted", "fake-scripted") and "not a language model" in a.reason


def test_breakdown_on_the_latest_plan_becomes_a_reroute_with_completed_stops():
    i = intent("Vehicle 0 broke down after its first stop. Replan it.")
    assert i["action"] == "reroute" and i["plan_id"] == "plan-0123456789ab"
    assert i["event"] == {"type": "vehicle_breakdown", "vehicle": 0, "completed": {"0": 1}}
    assert intent("vehicle 2 broke down after 3 stops on plan-ba9876543210")["event"]["completed"] == {"2": 3}
    assert intent("vehicle 2 broke down after 3 stops on plan-ba9876543210")["plan_id"] == "plan-ba9876543210"


def test_other_phrasings_and_refusals():
    assert intent("Customer 5 was not home, retry later.")["event"] == {
        "type": "failed_delivery", "customer_id": 5, "retry": True, "completed": {}}
    assert intent("Validate the latest plan.")["action"] == "validate"
    assert intent("Solve the latest plan with GA.")["engine"] == "ga"
    assert intent("Compare my plans")["plan_ids"] == ["plan-0123456789ab", "plan-ba9876543210"]
    assert intent("Move customer 3 to vehicle 1")["action"] == "refuse"  # never edits routes
    assert intent("What is the weather?")["action"] == "clarify"
    raw = ScriptedLLM().complete_json("(no plans yet)", [{"role": "user", "content": "validate"}], {})
    assert IntentEnvelope.model_validate_json(raw).intent.action == "clarify"


def test_api_breakdown_asks_for_confirmation_and_nothing_changes_until_confirmed(env):  # noqa: F811
    c, app, _fake, ha, _hb, pid = env
    app.state.copilot.llm = ScriptedLLM()
    assert c.get("/api/copilot/status", headers=ha).json()["model"] == "fake-scripted"
    before = len(c.get("/api/plans", headers=ha).json())
    r = c.post("/api/copilot/chat", json={"message": "Vehicle 0 broke down after its first stop. Replan it."},
               headers=ha).json()
    assert r["kind"] == "confirm" and r["pending_id"] and pid in r["text"] and "vehicle 0 broke down" in r["text"]
    assert len(c.get("/api/plans", headers=ha).json()) == before
    cancel = c.post("/api/copilot/confirm", json={"session_id": r["session_id"], "pending_id": r["pending_id"],
                                                  "approve": False}, headers=ha).json()
    assert cancel["kind"] != "error" and len(c.get("/api/plans", headers=ha).json()) == before
