"""Copilot on a public host (decision 0046): keys from the host's secrets only on request, a fast status with a clear
state, and limits that protect the server's key (per client IP, per session, per server and day, message length).
No test touches the network: hosted providers go through httpx.MockTransport."""
import datetime as dt
import json

import httpx
from app.copilot.limits import PUBLIC_DEFAULTS, CopilotLimits
from app.copilot.llm import PROBE_TIMEOUT_S, FakeLLM, GroqLLM, NoLLM, hosted_conf, llm_from_env

from tests.test_copilot import chat, env  # noqa: F401  (fixture: app with a solved plan for tenant A)
from tests.test_llm_providers import KEY, FakeHTTP, groq_ok

HOST = {"LOGIMIND_LLM_PROVIDER": "groq", "LOGIMIND_LLM_KEYS_FROM_ENV": "1", "GROQ_MODEL": "llama-3.3-70b-versatile"}


# ---- keys from the host's secrets -------------------------------------------------------------------------
def test_environment_keys_are_read_only_when_the_host_asks_for_it(tmp_path):
    empty = tmp_path / ".env"
    stray = {"LOGIMIND_LLM_PROVIDER": "groq", "GROQ_API_KEY": KEY, "GROQ_MODEL": "m"}
    assert llm_from_env(stray, empty).api_key == ""  # a global variable alone is never picked up
    llm = llm_from_env({**HOST, "GROQ_API_KEY": KEY}, empty)
    assert isinstance(llm, GroqLLM) and llm.api_key == KEY and llm.model == "llama-3.3-70b-versatile"
    assert llm.settings_from == "host" and KEY not in repr(llm)
    # base-URL overrides never come from the environment: the key goes only to Groq
    conf = hosted_conf(empty, {**HOST, "GROQ_API_KEY": KEY, "LOGIMIND_GROQ_BASE_URL": "http://localhost:1"})
    assert "LOGIMIND_GROQ_BASE_URL" not in conf
    assert llm_from_env({**HOST, "GROQ_API_KEY": KEY, "LOGIMIND_GROQ_BASE_URL": "http://localhost:1"},
                        empty).base_url == "https://api.groq.com/openai/v1"


def test_a_missing_secret_is_not_configured_at_once_without_a_request(tmp_path):
    http = FakeHTTP(groq_ok("{}"))
    llm = llm_from_env(HOST, tmp_path / ".env")
    llm.transport = http.transport
    d = llm.availability().to_dict()
    assert d["available"] is False and d["state"] == "not_configured"
    assert "GROQ_API_KEY secret is not set" in d["reason"] and "backend" not in d["reason"]
    assert http.requests == []
    assert NoLLM().availability().to_dict()["state"] == "not_configured"
    assert llm_from_env({"LOGIMIND_LLM_PROVIDER": "nonsense"}).availability().to_dict()["state"] == "unavailable"


def test_status_probe_uses_a_short_timeout_and_chat_the_normal_one():
    http = FakeHTTP(groq_ok(json.dumps({"intent": {"action": "clarify", "question": "Which plan?"}}),
                            model="llama-3.3-70b-versatile"))
    llm = GroqLLM(model="llama-3.3-70b-versatile", api_key=KEY, transport=http.transport, settings_from="host")
    d = llm.availability().to_dict()
    assert d["state"] == "ready" and d["available"] is True
    assert http.requests[0].extensions["timeout"]["read"] == PROBE_TIMEOUT_S <= 5
    llm.complete_json("SYSTEM", [{"role": "user", "content": "hi"}], {})
    assert http.requests[-1].extensions["timeout"]["read"] == llm.timeout_s == 30.0


def test_a_slow_provider_makes_status_unavailable_not_a_hang():
    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)
    llm = GroqLLM(model="m", api_key=KEY, transport=FakeHTTP(slow).transport, settings_from="host")
    d = llm.availability().to_dict()
    assert d["state"] == "unavailable" and f"within {PROBE_TIMEOUT_S:g} s" in d["reason"]


def test_status_endpoint_reports_state_and_message_limit(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    s = c.get("/api/copilot/status", headers=ha).json()
    assert s["state"] == "ready" and s["max_message_chars"] == 2000  # not a public demo: the usual length
    app.state.copilot.llm = NoLLM()
    s = c.get("/api/copilot/status", headers=ha).json()
    assert s["state"] == "not_configured" and s["available"] is False


# ---- limits -------------------------------------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def answer_fake(fake, pid):
    fake.respond = lambda system, messages: {"intent": {"action": "validate", "plan_id": pid}}


def post(c, h, msg="validate it", sid=None, ip=None):
    headers = {**h, **({"X-Forwarded-For": ip} if ip else {})}
    return c.post("/api/copilot/chat", json={"message": msg, "session_id": sid}, headers=headers)


def test_public_defaults_and_settings():
    lim = CopilotLimits.from_env(public=True, env={})
    assert lim.max_chars == PUBLIC_DEFAULTS["max_chars"] == 500 and lim.per_client and lim.overall and lim.daily
    off = CopilotLimits.from_env(public=False, env={})
    assert off.max_chars == 2000 and off.per_client is None and off.overall is None and off.daily is None
    custom = CopilotLimits.from_env(public=True, env={"LOGIMIND_COPILOT_PER_DAY": "0",
                                                      "LOGIMIND_COPILOT_MAX_CHARS": "300"})
    assert custom.daily is None and custom.max_chars == 300


def test_long_messages_are_refused_before_any_model_call(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    app.state.copilot_limits = CopilotLimits(0, 0, 0, max_chars=500)
    r = post(c, ha, "x" * 501)
    assert r.status_code == 400 and "limited to 500 characters" in r.json()["detail"]
    assert fake.calls == []
    answer_fake(fake, pid)
    assert post(c, ha, "x" * 500).status_code == 200


def test_per_client_limit_by_forwarded_ip_and_session(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    answer_fake(fake, pid)
    clock = Clock()
    app.state.copilot_limits = CopilotLimits(per_client=4, per_min=0, per_day=0, max_chars=500, clock=clock)
    # a burst of 2 per client (half a minute's messages)
    assert [post(c, ha, ip="10.0.0.1, 81.2.69.160").status_code for _ in range(2)] == [200, 200]
    r = post(c, ha, ip="10.0.0.1, 81.2.69.160")
    assert r.status_code == 429 and "too quickly" in r.json()["detail"] and int(r.headers["Retry-After"]) >= 1
    assert "Plans page" in r.json()["detail"]
    # a different visitor is not affected; a forged left-most entry does not give a new bucket
    assert post(c, ha, ip="9.9.9.9").status_code == 200
    assert post(c, ha, ip="1.2.3.4, 81.2.69.160").status_code == 429
    clock.t += 15  # 4 per minute: one message every 15 s
    assert post(c, ha, ip="81.2.69.160").status_code == 200
    # the same chat session from a "new" address is still limited
    clock.t += 60
    assert [post(c, ha, sid="s1", ip=f"81.2.70.{i}").status_code for i in range(3)] == [200, 200, 429]


def test_server_wide_per_minute_and_daily_caps(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    answer_fake(fake, pid)
    clock, day = Clock(), [dt.date(2026, 11, 13)]
    app.state.copilot_limits = CopilotLimits(0, per_min=4, per_day=3, max_chars=500, clock=clock,
                                             day_clock=lambda: day[0])
    codes = [post(c, ha, ip=f"81.2.70.{i}").status_code for i in range(3)]
    assert codes == [200, 200, 429]  # burst of 2 for the whole server
    assert "busy" in post(c, ha, ip="81.2.70.50").json()["detail"]
    clock.t += 120
    assert post(c, ha, ip="81.2.70.60").status_code == 200  # third and last message today
    clock.t += 120
    r = post(c, ha, ip="81.2.70.61")
    assert r.status_code == 429 and "today's message limit" in r.json()["detail"]
    day[0] = dt.date(2026, 11, 14)
    assert post(c, ha, ip="81.2.70.62").status_code == 200


def test_test_and_models_calls_count_too_but_status_does_not(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    app.state.copilot.llm = FakeLLM()
    app.state.copilot_limits = CopilotLimits(per_client=2, per_min=0, per_day=0, max_chars=500, clock=Clock())
    for _ in range(5):
        assert c.get("/api/copilot/status", headers=ha).status_code == 200
    assert c.post("/api/copilot/test", headers=ha).status_code == 200
    assert c.post("/api/copilot/models", headers=ha).status_code == 429
