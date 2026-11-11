""""Load models" for the Copilot settings box (decision 0035): the provider's list-models endpoint through the same
key header, outbound guard and limits; plain reasons when the list cannot be fetched; an empty model name picks the
first chat model and says so. Fake HTTP layer and fake DNS only: no network."""
import json
import logging

import httpx
import pytest
from app.copilot import netguard
from app.copilot.llm import LLMError, OllamaLLM, chat_models

from tests.test_copilot import env  # noqa: F401  (fixture: app with a solved plan for tenant A)
from tests.test_copilot_settings import KEY, headers, wired  # noqa: F401  (fake HTTP, fake DNS, tmp .env)

GROQ_LIST = {"data": [{"id": "whisper-large-v3"}, {"id": "openai/gpt-oss-20b"}, {"id": "llama-3.3-70b-versatile"},
                      {"id": "meta-llama/llama-guard-4-12b"}, {"id": "playai-tts"}, {"id": "llama-3.1-8b-instant"}]}
CHAT = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"]
GEMINI_LIST = {"models": [
    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/imagen-3.0-generate-002", "supportedGenerationMethods": ["predict"]}]}


def post_models(c, h, **s):
    r = c.post("/api/copilot/models", headers=headers(h, **s))
    assert r.status_code == 200, r.text
    return r


def test_groq_models_are_listed_with_the_key_only_in_a_header(wired, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)
    c, app, ha, hb, pid, use = wired
    http = use(lambda req: httpx.Response(200, json=GROQ_LIST))
    r = post_models(c, ha, provider="groq", key=KEY)
    out = r.json()
    assert out["ok"] is True and out["models"] == CHAT and "3 chat models found" in out["message"]
    assert len(http.requests) == 1 and http.requests[0].method == "GET"
    assert str(http.requests[0].url) == "https://api.groq.com/openai/v1/models"
    assert http.requests[0].headers["Authorization"] == f"Bearer {KEY}" and KEY not in str(http.requests[0].url)
    assert KEY not in r.text and KEY not in caplog.text


def test_gemini_models_come_from_its_own_list_endpoint(wired):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    http = use(lambda req: httpx.Response(200, json=GEMINI_LIST))
    out = post_models(c, ha, provider="gemini", key=KEY).json()
    assert out["ok"] is True and out["models"] == ["gemini-2.5-flash", "gemini-2.5-pro"]
    req = http.requests[0]
    assert req.url.path == "/v1beta/models" and req.url.params["pageSize"] == "1000"
    assert req.headers["x-goog-api-key"] == KEY and "key" not in str(req.url).lower().replace("pagesize", "")


def test_openai_compatible_lists_through_the_guard(wired):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    http = use(lambda req: httpx.Response(200, json={"data": [{"id": "m-2"}, {"id": "m-1"}]}))
    out = post_models(c, ha, provider="openai", key=KEY, base_url="https://llm.example.com/v1").json()
    assert out["models"] == ["m-1", "m-2"] and str(http.requests[0].url) == "https://llm.example.com/v1/models"
    blocked = post_models(c, ha, provider="openai", key=KEY, base_url="https://169.254.169.254/v1").json()
    assert blocked["ok"] is False and blocked["kind"] == "blocked" and "169.254.169.254" in blocked["message"]
    assert len(http.requests) == 1  # nothing was sent to the metadata address
    r = c.post("/api/copilot/models", headers=headers(ha, provider="openai", key=KEY, base_url="http://x.example"))
    assert r.status_code == 400 and "https://" in r.text and KEY not in r.text


@pytest.mark.parametrize("answer,kind,words", [
    (lambda r: httpx.Response(401, json={"error": {"message": f"Invalid API Key {KEY}"}}), "auth",
     "Groq rejected this key. Check that the whole key was copied, with no spaces or quotes."),
    (lambda r: httpx.Response(429, headers={"retry-after": "12"}), "rate_limit", "try again in 12 s"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down", request=r)), "network", "could not be reached"),
    (lambda r: httpx.Response(200, content=b"x" * (netguard.MAX_RESPONSE_BYTES + 1)), "bad_response", "1 MB"),
    (lambda r: httpx.Response(200, json={"data": [{"id": "whisper-large-v3"}]}), "model", "no chat models"),
    (lambda r: httpx.Response(302, headers={"location": "http://10.0.0.1/"}), "bad_request", "redirect"),
])
def test_a_list_that_cannot_be_fetched_gives_a_plain_reason(wired, answer, kind, words):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    use(answer)
    r = post_models(c, ha, provider="groq", key=KEY)
    out = r.json()
    assert out["ok"] is False and out["kind"] == kind and words in out["message"] and out["models"] == []
    assert KEY not in r.text


def test_no_key_anywhere_is_a_plain_reason_without_a_request(wired):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    app.state.llm_dotenv.write_text("", encoding="utf-8")  # no Groq key in backend/.env either
    http = use(lambda r: pytest.fail("no request without a key"))
    out = post_models(c, ha, provider="groq").json()
    assert out["ok"] is False and out["kind"] == "auth" and "key missing or rejected" in out["message"]
    assert http.requests == []


def test_an_empty_model_name_uses_a_suitable_chat_model_and_says_which(wired):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    app.state.llm_dotenv.write_text("", encoding="utf-8")  # no model in backend/.env: the console gave none

    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json=GROQ_LIST)
        body = json.loads(req.content)
        intent = {"intent": {"action": "explain", "plan_id": pid}}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(intent)}}],
                                         "model_used": body["model"]})
    http = use(answer)
    test = c.post("/api/copilot/test", headers=headers(ha, provider="groq", key=KEY)).json()
    # Groq's list has openai/gpt-oss-20b, the first of its preferred chat models (decision 0036)
    assert test["ok"] is True and test["model"] == "openai/gpt-oss-20b" and test["chosen_automatically"] is True
    assert test["message"] == ("Works: Groq is ready, using openai/gpt-oss-20b (chosen automatically: a common chat "
                               "model).")
    assert all(q.method == "GET" for q in http.requests)  # never a completion to test
    status = c.get("/api/copilot/status", headers=headers(ha, provider="groq", key=KEY)).json()
    assert status["available"] is True and status["model"] == "openai/gpt-oss-20b"
    assert "chosen automatically" in status["reason"]
    r = c.post("/api/copilot/chat", json={"message": "explain the latest plan"},
               headers=headers(ha, provider="groq", key=KEY)).json()
    assert r["kind"] == "answer"
    posts = [q for q in http.requests if q.method == "POST"]
    assert posts and all(json.loads(q.content)["model"] == "openai/gpt-oss-20b" for q in posts)


def test_a_typed_model_name_is_never_replaced(wired):  # noqa: F811
    c, app, ha, hb, pid, use = wired
    use(lambda req: httpx.Response(200, json=GROQ_LIST))
    out = c.post("/api/copilot/test", headers=headers(ha, provider="groq", key=KEY, model="not-in-list")).json()
    assert out["ok"] is False and out["kind"] == "model" and "not-in-list" in out["message"]


def test_ollama_lists_its_installed_models(monkeypatch):
    tags = {"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text:latest"}, {"name": "qwen2.5:7b"}]}
    monkeypatch.setattr(httpx, "get", lambda url, timeout: httpx.Response(200, json=tags,
                                                                       request=httpx.Request("GET", url)))
    assert OllamaLLM().list_models() == ["llama3.2:3b", "qwen2.5:7b"]

    def down(url, timeout):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "get", down)
    with pytest.raises(LLMError) as exc:
        OllamaLLM().list_models()
    assert exc.value.kind == "network" and "not running" in str(exc.value)


def test_the_list_is_cleaned_and_limited():
    names = [f"m-{i:04d}" for i in range(700)] + ["x" * 201, "bad\nname", None, 7, "text-embedding-3-small"]
    out = chat_models(names)
    assert len(out) == 500 and out[0] == "m-0000" and all(len(n) <= 200 and n.isprintable() for n in out)
