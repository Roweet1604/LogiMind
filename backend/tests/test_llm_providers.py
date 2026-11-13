"""Optional hosted LLM providers (decision 0032): Groq and Gemini through a FAKE HTTP layer (httpx.MockTransport).
No test touches the network. Checks the request shape (schema-constrained JSON, key only in a header), plain errors
for a missing / rejected key, rate limits, network and server errors, that the key never leaks, and that the
copilot keeps validation, the single retry and the clarifying question."""
import json
import logging
import re
from pathlib import Path

import httpx
import pytest
from app.copilot.llm import (
    GeminiLLM,
    GroqLLM,
    LLMError,
    LLMUnavailable,
    NoLLM,
    OllamaLLM,
    llm_from_env,
    portable_schema,
    read_dotenv,
)
from app.copilot.schemas import IntentEnvelope

from tests.test_copilot import chat, env  # noqa: F401  (fixture: app with a solved plan for tenant A)

KEY = "gsk_TESTKEY_not_real_0123456789"
SCHEMA = IntentEnvelope.model_json_schema()
ROOT = Path(__file__).resolve().parents[2]


class FakeHTTP:
    """Records every request; `answer(request)` returns an httpx.Response (or raises a transport error)."""

    def __init__(self, answer):
        self.answer, self.requests = answer, []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.answer(request)


def groq_ok(content, model="openai/gpt-oss-20b"):
    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": model}, {"id": "other"}]})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})
    return answer


def gemini_ok(content):
    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json={"name": "models/gemini-2.5-flash"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": content}]}}]})
    return answer


def groq(http, model="openai/gpt-oss-20b", key=KEY):
    return GroqLLM(model=model, api_key=key, transport=http.transport)


def gemini(http, key=KEY):
    return GeminiLLM(model="gemini-2.5-flash", api_key=key, transport=http.transport)


# ---- configuration -----------------------------------------------------------------------------------------
def test_provider_selection_and_settings_come_from_backend_env_only(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"# comment\nGROQ_API_KEY={KEY}\nGROQ_MODEL=openai/gpt-oss-20b\nGEMINI_API_KEY=\"g-key\"\n"
                      "GEMINI_MODEL=gemini-2.5-flash\n", encoding="utf-8")
    assert read_dotenv(dotenv)["GEMINI_API_KEY"] == "g-key"
    g = llm_from_env({"LOGIMIND_LLM_PROVIDER": "groq"}, dotenv)
    assert isinstance(g, GroqLLM) and g.model == "openai/gpt-oss-20b" and g.api_key == KEY
    assert g.base_url == "https://api.groq.com/openai/v1"
    m = llm_from_env({"LOGIMIND_LLM_PROVIDER": "Gemini"}, dotenv)
    assert isinstance(m, GeminiLLM) and m.api_key == "g-key"
    # a key in the GLOBAL environment is ignored: only backend/.env counts
    monkeypatch.setenv("GROQ_API_KEY", "from-global-env")
    empty = tmp_path / "empty.env"
    empty.write_text("", encoding="utf-8")
    assert llm_from_env({"LOGIMIND_LLM_PROVIDER": "groq"}, empty).api_key == ""
    # Ollama stays the default; unknown names are refused plainly
    assert isinstance(llm_from_env({}, dotenv), OllamaLLM)
    assert isinstance(llm_from_env({"LOGIMIND_LLM_PROVIDER": "none"}, dotenv), NoLLM)
    bad = llm_from_env({"LOGIMIND_LLM_PROVIDER": "openai"}, dotenv)
    assert isinstance(bad, NoLLM) and "expected ollama, groq, gemini, scripted or none" in bad.availability().reason


def test_missing_key_or_model_is_a_plain_message_and_no_request_is_made():
    http = FakeHTTP(lambda r: pytest.fail("no request without a key"))
    av = GroqLLM(model="m", api_key="", transport=http.transport).availability()
    assert not av.available and av.problem == "Groq key missing or rejected"
    assert "GROQ_API_KEY is empty in backend\\.env" in av.reason
    av = GeminiLLM(model="", api_key=KEY, transport=http.transport).availability()
    assert not av.available and av.problem == "Gemini model not set" and "GEMINI_MODEL" in av.reason
    with pytest.raises(LLMUnavailable):
        GroqLLM(model="m", api_key="", transport=http.transport).complete_json("s", [], SCHEMA)
    assert http.requests == []


def test_a_base_url_override_is_accepted_only_for_this_computer(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"GROQ_API_KEY={KEY}\nGROQ_MODEL=m\nLOGIMIND_GROQ_BASE_URL=https://evil.example/v1\n")
    refused = llm_from_env({"LOGIMIND_LLM_PROVIDER": "groq"}, dotenv)
    assert isinstance(refused, NoLLM) and "localhost" in refused.availability().reason
    dotenv.write_text(f"GROQ_API_KEY={KEY}\nGROQ_MODEL=m\nLOGIMIND_GROQ_BASE_URL=http://127.0.0.1:8098/v1/\n")
    assert llm_from_env({"LOGIMIND_LLM_PROVIDER": "groq"}, dotenv).base_url == "http://127.0.0.1:8098/v1"


def test_env_example_documents_the_settings_with_empty_values_and_env_is_git_ignored():
    text = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    for var in ("GROQ_API_KEY", "GROQ_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL"):
        assert re.search(rf"^{var}=$", text, re.MULTILINE), var
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()


# ---- request shape -------------------------------------------------------------------------------------------
def test_groq_request_uses_json_schema_output_and_the_key_only_in_the_header():
    http = FakeHTTP(groq_ok('{"intent": {"action": "clarify", "question": "Which plan?"}}'))
    out = groq(http).complete_json("SYSTEM", [{"role": "user", "content": "hi"}], SCHEMA)
    assert json.loads(out)["intent"]["action"] == "clarify"
    req = http.requests[-1]
    assert str(req.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert req.headers["Authorization"] == f"Bearer {KEY}" and KEY not in str(req.url)
    body = json.loads(req.content)
    assert body["temperature"] == 0 and body["model"] == "openai/gpt-oss-20b"
    assert body["messages"][0] == {"role": "system", "content": "SYSTEM"} and body["messages"][1]["content"] == "hi"
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"] == portable_schema(SCHEMA)
    assert "discriminator" not in json.dumps(rf) and KEY not in req.content.decode()


def test_gemini_request_uses_response_json_schema_and_the_key_only_in_the_header():
    http = FakeHTTP(gemini_ok('{"intent": {"action": "refuse", "reason": "editing routes by hand"}}'))
    out = gemini(http).complete_json("SYSTEM", [{"role": "user", "content": "a"}, {"role": "assistant",
                                                                                  "content": "b"}], SCHEMA)
    assert json.loads(out)["intent"]["action"] == "refuse"
    req = http.requests[-1]
    assert str(req.url) == ("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash"
                            ":generateContent")
    assert req.headers["x-goog-api-key"] == KEY and "key=" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYSTEM"
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    cfg = body["generationConfig"]
    assert cfg["temperature"] == 0 and cfg["responseMimeType"] == "application/json"
    assert cfg["responseJsonSchema"] == portable_schema(SCHEMA)


def test_availability_probes_once_then_uses_the_cache():
    http = FakeHTTP(groq_ok("{}"))
    llm = groq(http)
    assert llm.availability().available and llm.availability().available
    assert len(http.requests) == 1
    http2 = FakeHTTP(groq_ok("{}", model="something-else"))
    av = groq(http2).availability()
    assert not av.available and "not found in its model list" in av.reason and av.problem == "Groq model not found"


# ---- errors: shown as what they are, never with the key ---------------------------------------------------
@pytest.mark.parametrize("make,expected_kind,words", [
    (lambda r: httpx.Response(401, json={"error": {"message": f"Invalid API Key {KEY}"}}), "auth",
     "Groq key missing or rejected (HTTP 401)"),
    (lambda r: httpx.Response(403, json={"error": {"message": "forbidden"}}), "auth", "key missing or rejected"),
    (lambda r: httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "slow down"}}),
     "rate_limit", "rate limit reached (HTTP 429); try again in 7 s"),
    (lambda r: httpx.Response(503, text="upstream down"), "server", "server problem (HTTP 503)"),
    (lambda r: httpx.Response(404, json={"error": {"message": "model not found"}}), "model",
     "model 'openai/gpt-oss-20b' not found (HTTP 404)"),
    (lambda r: httpx.Response(400, json={"error": {"message": f"bad schema near {KEY}"}}), "bad_request",
     "refused the request (HTTP 400): bad schema near ***"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("no route", request=r)), "network", "could not be reached"),
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)), "network", "did not answer within"),
])
def test_groq_errors_are_plain_and_never_contain_the_key(make, expected_kind, words, caplog):
    caplog.set_level(logging.DEBUG)
    http = FakeHTTP(make)
    with pytest.raises(LLMError) as exc:
        groq(http).complete_json("s", [{"role": "user", "content": "x"}], SCHEMA)
    assert exc.value.kind == expected_kind and words in str(exc.value)
    assert KEY not in str(exc.value) and KEY not in caplog.text


def test_gemini_invalid_key_answer_400_is_reported_as_a_rejected_key():
    invalid = {"error": {"message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}
    http = FakeHTTP(lambda r: httpx.Response(400, json=invalid))
    with pytest.raises(LLMError) as exc:
        gemini(http).complete_json("s", [{"role": "user", "content": "x"}], SCHEMA)
    assert exc.value.kind == "auth" and "Gemini key missing or rejected" in str(exc.value)
    av = gemini(http).availability()
    assert not av.available and av.problem == "Gemini key missing or rejected"


def test_gemini_blocked_answer_is_an_error_not_a_crash():
    http = FakeHTTP(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(LLMError) as exc:
        gemini(http).complete_json("s", [{"role": "user", "content": "x"}], SCHEMA)
    assert exc.value.kind == "bad_response" and "SAFETY" in str(exc.value)


# ---- through the copilot: invariants kept --------------------------------------------------------------------
def _plan_id_from(body: dict) -> str:
    text = body["messages"][0]["content"]
    return re.search(r"plan-[0-9a-f]{12}", text).group(0)


def test_copilot_with_groq_answers_from_the_tool_and_the_status_never_shows_the_key(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-20b"}]})
        body = json.loads(req.content)
        intent = {"intent": {"action": "explain", "plan_id": _plan_id_from(body)}}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(intent)}}]})
    http = FakeHTTP(answer)
    app.state.copilot.llm = groq(http)
    status = c.get("/api/copilot/status", headers=ha)
    assert status.json()["provider"] == "groq" and status.json()["model"] == "openai/gpt-oss-20b"
    assert status.json()["available"] is True and KEY not in status.text
    r = chat(c, ha, "explain the latest plan")
    assert r["kind"] == "answer" and r["tool_calls"][0]["tool"] == "explain"
    assert r["tool_calls"][0]["output"]["plan_id"] == pid and KEY not in json.dumps(r)


def test_copilot_keeps_one_retry_then_the_clarifying_question_with_a_hosted_provider(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    http = FakeHTTP(groq_ok('{"intent": {"action": "write_routes", "routes": [[1, 2]]}}'))
    app.state.copilot.llm = groq(http)
    r = chat(c, ha, "put customer 3 first on vehicle 1")
    assert r["kind"] == "clarify" and r["parse_attempts"] == 2
    posts = [q for q in http.requests if q.method == "POST"]
    assert len(posts) == 2  # exactly one retry
    assert "That output was invalid" in json.loads(posts[1].content)["messages"][-1]["content"]


def test_a_rejected_key_or_a_rate_limit_is_a_reply_not_a_crash(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    def rejected(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-20b"}]})
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
    app.state.copilot.llm = groq(FakeHTTP(rejected))
    r = chat(c, ha, "explain the latest plan")
    assert r["kind"] == "unavailable" and r["llm_error"] == "auth"
    assert r["text"].startswith("Groq key missing or rejected")
    s = c.get("/api/copilot/status", headers=ha).json()  # the status now shows the rejected key at once
    assert s["available"] is False and s["problem"] == "Groq key missing or rejected"

    def limited(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-20b"}]})
        return httpx.Response(429, headers={"retry-after": "20"})
    app.state.copilot.llm = groq(FakeHTTP(limited))
    r = chat(c, ha, "explain the latest plan")
    assert r["kind"] == "error" and r["llm_error"] == "rate_limit" and "try again in 20 s" in r["text"]

    def offline(req):
        raise httpx.ConnectError("offline", request=req)
    app.state.copilot.llm = groq(FakeHTTP(offline))
    s = c.get("/api/copilot/status", headers=ha).json()
    assert s["available"] is False and s["problem"] == "Groq not reachable"
    r = chat(c, ha, "explain the latest plan")
    assert r["kind"] == "unavailable" and "could not be reached" in r["text"]


def test_the_llm_cannot_hand_over_routes_through_a_hosted_provider(env):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    before = len(c.get("/api/plans", headers=ha).json())
    http = FakeHTTP(groq_ok(json.dumps({"intent": {"action": "solve", "plan_id": pid, "engine": "ortools",
                                                    "routes": [[3, 2, 1]]}})))
    app.state.copilot.llm = groq(http)
    r = chat(c, ha, "use these routes: 3, 2, 1")
    assert r["kind"] == "clarify"  # extra="forbid": a route field makes the output invalid, twice
    assert len(c.get("/api/plans", headers=ha).json()) == before
