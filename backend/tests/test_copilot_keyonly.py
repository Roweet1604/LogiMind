"""Key-only Copilot settings (decision 0036): the console detects the provider from the key's prefix and sends one
provider; the server routes it to that provider only, picks a suitable chat model (free ones first), and answers in
one plain sentence. Fake HTTP layer and fake DNS only: no network."""
import json
import logging

import httpx
import pytest
from app.copilot.llm import chat_models, llm_from_settings, pick_model

from tests.test_copilot import env  # noqa: F401  (fixture: app with a solved plan for tenant A)
from tests.test_copilot_settings import FakeHTTP, headers, wired  # noqa: F401

PUBLIC = "93.184.216.34"
HOSTS = ["api.groq.com", "generativelanguage.googleapis.com", "openrouter.ai", "api.openai.com", "llm.example.com"]
KEYS = {"groq": "gsk_FAKE_key_0001", "gemini": "AIzaFAKE_key_0002", "openrouter": "sk-or-v1-FAKE0003",
        "openai": "sk-proj-FAKE_key_0004"}
LISTS = {
    "groq": {"data": [{"id": "whisper-large-v3"}, {"id": "llama-3.1-8b-instant"}, {"id": "openai/gpt-oss-20b"}]},
    "gemini": {"models": [{"name": "models/gemini-1.0-pro", "supportedGenerationMethods": ["generateContent"]},
                          {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                          {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]},
    "openrouter": {"data": [{"id": "anthropic/claude-sonnet-4"}, {"id": "meta-llama/llama-3.3-70b-instruct:free"},
                            {"id": "deepseek/deepseek-chat-v3:free"}, {"id": "openai/gpt-4o"}]},
    "openai": {"data": [{"id": "babbage-002"}, {"id": "davinci-002"}, {"id": "gpt-4o"}, {"id": "gpt-4o-mini"},
                        {"id": "gpt-4o-realtime-preview"}, {"id": "text-embedding-3-small"}, {"id": "o3"}]},
}
CHOSEN = {"groq": ("openai/gpt-oss-20b", "a common chat model"), "gemini": ("gemini-2.5-flash", "a common chat model"),
          "openrouter": ("deepseek/deepseek-chat-v3:free", "a free model"),
          "openai": ("gpt-4o-mini", "a common chat model")}
LIST_URL = {"groq": "https://api.groq.com/openai/v1/models",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
            "openrouter": "https://openrouter.ai/api/v1/models", "openai": "https://api.openai.com/v1/models"}
LABEL = {"groq": "Groq", "gemini": "Gemini", "openrouter": "OpenRouter", "openai": "OpenAI"}


@pytest.fixture
def routed(wired):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    app.state.llm_dotenv.write_text("", encoding="utf-8")  # nothing from backend/.env: only the console's settings
    app.state.llm_resolve = lambda host, port: [PUBLIC] if host in HOSTS else pytest.fail(f"unexpected host {host}")
    return c, app, ha, pid, use


@pytest.mark.parametrize("provider", ["groq", "gemini", "openrouter", "openai"])
def test_each_detected_provider_goes_to_its_own_list_and_gets_a_suitable_model(routed, provider, caplog):
    caplog.set_level(logging.DEBUG)
    c, app, ha, pid, use = routed
    http = use(lambda req: httpx.Response(200, json=LISTS[provider]))
    r = c.post("/api/copilot/test", headers=headers(ha, provider=provider, key=KEYS[provider]))
    out = r.json()
    model, why = CHOSEN[provider]
    assert out["ok"] is True and out["model"] == model and out["chosen_automatically"] is True
    assert out["message"] == f"Works: {LABEL[provider]} is ready, using {model} (chosen automatically: {why})."
    assert [str(q.url) for q in http.requests] == [LIST_URL[provider]]  # one call, to this provider only
    q = http.requests[0]
    sent = q.headers.get("Authorization") or q.headers.get("x-goog-api-key")
    assert KEYS[provider] in sent and KEYS[provider] not in str(q.url)
    assert KEYS[provider] not in r.text and KEYS[provider] not in caplog.text
    status = c.get("/api/copilot/status", headers=headers(ha, provider=provider, key=KEYS[provider],
                                                           model=model)).json()
    assert status["provider"] == provider and status["model"] == model


def test_an_anthropic_key_is_refused_plainly_and_nothing_is_sent(routed):
    c, app, ha, pid, use = routed
    http = use(lambda req: pytest.fail("nothing may be sent for an Anthropic key"))
    r = c.post("/api/copilot/test", headers=headers(ha, provider="anthropic", key="sk-ant-api03-FAKE"))
    assert r.status_code == 400 and "Anthropic keys are not supported yet" in r.text and "sk-ant" not in r.text
    assert http.requests == []


@pytest.mark.parametrize("provider", ["groq", "gemini", "openrouter", "openai"])
def test_a_401_is_one_plain_sentence_naming_the_provider(routed, provider):
    c, app, ha, pid, use = routed
    use(lambda req: httpx.Response(401, json={"error": {"message": f"invalid key {KEYS[provider]}"}}))
    r = c.post("/api/copilot/test", headers=headers(ha, provider=provider, key=KEYS[provider]))
    out = r.json()
    assert out["ok"] is False and out["kind"] == "auth"
    assert out["message"] == (f"{LABEL[provider]} rejected this key. Check that the whole key was copied, with no "
                              "spaces or quotes.")
    assert KEYS[provider] not in r.text


def test_a_provider_outage_says_it_is_the_provider_not_logimind(routed):
    c, app, ha, pid, use = routed
    use(lambda req: (_ for _ in ()).throw(httpx.ConnectError("down", request=req)))
    out = c.post("/api/copilot/test", headers=headers(ha, provider="openrouter", key=KEYS["openrouter"])).json()
    assert out["kind"] == "network" and out["message"].startswith(
        "OpenRouter could not be reached from the LogiMind server (ConnectError)")


def test_the_chosen_model_is_used_for_the_chat(routed):
    c, app, ha, pid, use = routed

    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json=LISTS["openrouter"])
        intent = {"intent": {"action": "explain", "plan_id": pid}}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(intent)}}]})
    http = use(answer)
    r = c.post("/api/copilot/chat", json={"message": "explain the latest plan"},
               headers=headers(ha, provider="openrouter", key=KEYS["openrouter"])).json()
    assert r["kind"] == "answer"
    posts = [q for q in http.requests if q.method == "POST"]
    assert posts and all(json.loads(q.content)["model"] == "deepseek/deepseek-chat-v3:free" for q in posts)
    assert all(str(q.url).startswith("https://openrouter.ai/api/v1/") for q in http.requests)


def test_model_choice_order_free_then_preferred_then_first():
    assert pick_model("openrouter", chat_models(["z/x", "b/y:free", "a/z:free"])) == ("a/z:free", "free")
    assert pick_model("openai", chat_models(["babbage-002", "gpt-4o", "gpt-4o-mini"])) == ("gpt-4o-mini", "preferred")
    assert pick_model("groq", chat_models(["zzz", "llama-3.1-8b-instant"])) == ("llama-3.1-8b-instant", "preferred")
    assert pick_model("openai", chat_models(["my-model-b", "my-model-a"])) == ("my-model-a", "first")
    assert chat_models(LISTS["openai"]["data"] and [m["id"] for m in LISTS["openai"]["data"]]) == \
        ["gpt-4o", "gpt-4o-mini", "o3"]  # completion-only, realtime and embedding models left out


def test_openai_and_openrouter_defaults_and_the_operator_override(tmp_path):
    none = tmp_path / "none.env"
    o = llm_from_settings({"provider": "openai", "key": "sk-x"}, dotenv=none)
    assert (o.base_url, o.label, o.provider, o.guarded) == ("https://api.openai.com/v1", "OpenAI", "openai", True)
    r = llm_from_settings({"provider": "openrouter", "key": "sk-or-x"}, dotenv=none)
    assert (r.base_url, r.label, r.provider, r.guarded) == ("https://openrouter.ai/api/v1", "OpenRouter",
                                                            "openrouter", True)
    other = llm_from_settings({"provider": "openai", "key": "sk-x", "base_url": "https://llm.example.com/v1"},
                              dotenv=none)
    assert other.label == "OpenAI-compatible service" and other.guarded is True
    local = tmp_path / ".env"
    local.write_text("LOGIMIND_OPENROUTER_BASE_URL=http://127.0.0.1:8097/openrouter/api/v1\n", encoding="utf-8")
    fake = llm_from_settings({"provider": "openrouter", "key": "sk-or-x"}, dotenv=local)
    assert fake.base_url == "http://127.0.0.1:8097/openrouter/api/v1" and fake.guarded is False
    local.write_text("LOGIMIND_OPENROUTER_BASE_URL=https://evil.example/v1\n", encoding="utf-8")
    assert llm_from_settings({"provider": "openrouter", "key": "k"}, dotenv=local).base_url == \
        "https://openrouter.ai/api/v1"  # a non-local override is ignored: the key never goes elsewhere
