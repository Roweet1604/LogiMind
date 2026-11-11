"""Copilot settings from the console (decision 0033): provider, model, key and base URL arrive as headers with each
request. Tries to break the outbound-request guard (SSRF), checks that the key is never stored, logged, audited or
returned, that the console's settings win over backend/.env, and that the copilot's invariants and tenant isolation
hold. Fake HTTP layer (httpx.MockTransport) and fake DNS only: no network."""
import json
import logging

import httpcore
import httpx
import pytest
from app.copilot import netguard
from app.copilot.llm import GroqLLM, OpenAICompatLLM, SettingsError, llm_from_settings
from app.copilot.netguard import BlockedURL, PinnedBackend, check_base_url, check_public, is_blocked_ip
from app.db.models import AuditLog
from app.db.session import admin_session
from sqlalchemy import select

from tests.test_copilot import env  # noqa: F401  (fixture: app with a solved plan for tenant A, FakeLLM default)

KEY = "sk-ui-SECRET-not-real-9f8e7d6c5b4a"
PUBLIC = "93.184.216.34"


def fake_dns(table):
    def resolve(host, port):
        if host not in table:
            raise BlockedURL(f"the host name {host!r} could not be found (check the base URL)")
        return table[host]
    return resolve


DNS = fake_dns({"api.groq.com": [PUBLIC], "llm.example.com": [PUBLIC], "generativelanguage.googleapis.com": [PUBLIC],
                "evil-rebind.example": [PUBLIC, "10.0.0.7"], "internal.example": ["192.168.1.20"],
                "metadata.google.internal": ["169.254.169.254"], "v6meta.example": ["fd00:ec2::254"]})


class FakeHTTP:
    def __init__(self, answer):
        self.answer, self.requests = answer, []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        self.requests.append(request)
        return self.answer(request)


def openai_answer(model="m-1", content=None):
    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": model}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content or "{}"}}]})
    return answer


def headers(h, **s):
    names = {"provider": "X-LLM-Provider", "model": "X-LLM-Model", "base_url": "X-LLM-Base-URL", "key": "X-LLM-Key"}
    return {**h, **{names[k]: v for k, v in s.items()}}


@pytest.fixture
def wired(env, tmp_path):  # noqa: F811
    c, app, fake, ha, hb, pid = env
    dotenv = tmp_path / "backend.env"
    dotenv.write_text("GROQ_API_KEY=env-groq-key\nGROQ_MODEL=env-model\n", encoding="utf-8")
    app.state.llm_dotenv, app.state.llm_resolve = dotenv, DNS

    def use(answer):
        http = FakeHTTP(answer)
        app.state.llm_transport = http.transport
        return http
    return c, app, ha, hb, pid, use


# ---- SSRF: shape and address checks ---------------------------------------------------------------------------
@pytest.mark.parametrize("url,words", [
    ("http://llm.example.com/v1", "must start with https://"),
    ("https://user:pw@llm.example.com/v1", "user name or password"),
    ("https://llm.example.com/v1?x=1", "must not contain ? or #"),
    ("https:///v1", "no host name"),
    ("https://llm.example.com:99999/v1", "invalid port"),
    ("", "missing"),
    ("ftp://llm.example.com", "must start with https://"),
])
def test_base_url_shape_is_checked(url, words):
    with pytest.raises(BlockedURL) as exc:
        check_base_url(url)
    assert words in str(exc.value)


@pytest.mark.parametrize("ip", ["169.254.169.254", "10.0.0.5", "127.0.0.1", "192.168.1.1", "172.16.0.1",
                                "100.100.100.200", "0.0.0.0", "::1", "fd00:ec2::254", "::ffff:10.0.0.1",
                                "::ffff:169.254.169.254", "224.0.0.1", "fe80::1", "255.255.255.255"])
def test_private_loopback_link_local_metadata_and_multicast_addresses_are_blocked(ip):
    assert is_blocked_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(ip):
    assert not is_blocked_ip(ip)


@pytest.mark.parametrize("host", ["metadata.google.internal", "internal.example", "evil-rebind.example",
                                  "v6meta.example", "169.254.169.254", "127.0.0.1", "10.1.2.3"])
def test_a_host_that_resolves_to_any_internal_address_is_blocked(host):
    resolve = fake_dns({**{h: v for h, v in [("metadata.google.internal", ["169.254.169.254"]),
                                            ("internal.example", ["192.168.1.20"]),
                                            ("evil-rebind.example", [PUBLIC, "10.0.0.7"]),
                                            ("v6meta.example", ["fd00:ec2::254"])]},
                        "169.254.169.254": ["169.254.169.254"], "127.0.0.1": ["127.0.0.1"], "10.1.2.3": ["10.1.2.3"]})
    with pytest.raises(BlockedURL) as exc:
        check_public(host, 443, resolve)
    assert "private or internal network address" in str(exc.value)


def test_unknown_host_names_are_a_plain_error():
    with pytest.raises(BlockedURL) as exc:
        check_public("nope.invalid", 443, DNS)
    assert "could not be found" in str(exc.value)


def test_the_connection_is_pinned_to_the_checked_address(monkeypatch):
    seen = []
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", lambda self, host, port, **kw: seen.append((host, port)))
    backend = PinnedBackend({"llm.example.com": PUBLIC})
    backend.connect_tcp("llm.example.com", 443)
    assert seen == [(PUBLIC, 443)]  # the checked IP, not a fresh (possibly rebound) DNS answer
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("other.example.com", 443)  # anything not checked is refused


def test_every_call_checks_again_so_a_later_dns_change_is_caught():
    answers = iter([[PUBLIC], ["10.0.0.9"]])
    llm = OpenAICompatLLM(model="m-1", api_key=KEY, base_url="https://llm.example.com/v1", guarded=True,
                          transport=FakeHTTP(openai_answer()).transport, resolve=lambda h, p: next(answers))
    assert llm.test_connection()["ok"] is True
    second = llm.test_connection()
    assert second["ok"] is False and second["kind"] == "blocked" and "10.0.0.9" in second["message"]


def test_redirects_are_not_followed_and_huge_answers_are_refused():
    http = FakeHTTP(lambda r: httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"}))
    llm = OpenAICompatLLM(model="m-1", api_key=KEY, base_url="https://llm.example.com/v1", guarded=True,
                          transport=http.transport, resolve=DNS)
    out = llm.test_connection()
    assert out["ok"] is False and "redirect" in out["message"] and len(http.requests) == 1
    big = FakeHTTP(lambda r: httpx.Response(200, content=b"x" * (netguard.MAX_RESPONSE_BYTES + 10)))
    llm.transport = big.transport
    out = llm.test_connection()
    assert out["ok"] is False and out["kind"] == "bad_response" and "1 MB" in out["message"]


# ---- through the API ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("base,kind,words", [
    ("https://169.254.169.254/latest/meta-data", "blocked", "private or internal network address (169.254.169.254)"),
    ("https://10.0.0.5/v1", "blocked", "(10.0.0.5)"),
    ("https://127.0.0.1:8000/api", "blocked", "(127.0.0.1)"),
    ("https://internal.example/v1", "blocked", "(192.168.1.20)"),
    ("https://evil-rebind.example/v1", "blocked", "(10.0.0.7)"),
    ("https://metadata.google.internal/computeMetadata/v1", "blocked", "(169.254.169.254)"),
])
def test_test_connection_blocks_internal_targets_without_sending_anything(wired, base, kind, words):
    c, app, ha, hb, pid, use = wired
    http = use(lambda r: pytest.fail("no request may reach an internal address"))
    r = c.post("/api/copilot/test", headers=headers(ha, provider="openai", model="m-1", key=KEY, base_url=base))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is False and out["kind"] == kind and words in out["message"]
    assert http.requests == [] and KEY not in r.text


@pytest.mark.parametrize("base,words", [("http://llm.example.com/v1", "must start with https://"),
                                        ("http://localhost:11434/v1", "must start with https://"),
                                        ("https://u:p@llm.example.com", "user name or password")])
def test_bad_base_urls_are_refused_with_a_plain_400(wired, base, words):
    c, app, ha, hb, pid, use = wired
    r = c.post("/api/copilot/test", headers=headers(ha, provider="openai", model="m", key=KEY, base_url=base))
    assert r.status_code == 400 and words in r.text and KEY not in r.text


@pytest.mark.parametrize("answer,ok,kind,words", [
    (openai_answer("m-1"), True, "ok", "Works"),
    (lambda r: httpx.Response(401, json={"error": {"message": f"bad key {KEY}"}}), False, "auth",
     "OpenAI-compatible service rejected this key. Check that the whole key was copied, with no spaces or quotes."),
    (openai_answer("another-model"), False, "model", "model 'm-1' not found"),
    (lambda r: httpx.Response(429, headers={"retry-after": "30"}), False, "rate_limit", "try again in 30 s"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down", request=r)), False, "network", "could not be reached"),
])
def test_test_connection_gives_plain_results_and_never_the_key(wired, caplog, answer, ok, kind, words):
    caplog.set_level(logging.DEBUG)
    c, app, ha, hb, pid, use = wired
    http = use(answer)
    r = c.post("/api/copilot/test", headers=headers(ha, provider="openai", model="m-1", key=KEY,
                                                    base_url="https://llm.example.com/v1"))
    out = r.json()
    assert out["ok"] is ok and out["kind"] == kind and words in out["message"], out
    assert len(http.requests) == 1 and http.requests[0].method == "GET"  # one minimal call, never a completion
    assert http.requests[0].headers["Authorization"] == f"Bearer {KEY}" and KEY not in str(http.requests[0].url)
    assert KEY not in r.text and KEY not in caplog.text


def test_a_rejected_header_never_echoes_the_value(wired):
    c, app, ha, hb, pid, use = wired
    long_key = "sk-" + "A" * 600
    r = c.post("/api/copilot/test", headers=headers(ha, provider="groq", model="m", key=long_key))
    assert r.status_code == 400 and "key is too long" in r.text and long_key not in r.text and "AAAA" not in r.text
    r = c.post("/api/copilot/test", headers=headers(ha, provider="anthropic-magic", key=KEY))
    assert r.status_code == 400 and "unknown provider" in r.text and KEY not in r.text


def test_console_settings_win_and_backend_env_fills_the_gaps(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("GROQ_API_KEY=env-key\nGROQ_MODEL=env-model\n", encoding="utf-8")
    ui = llm_from_settings({"provider": "groq", "key": KEY, "model": "ui-model"}, dotenv=dotenv)
    assert isinstance(ui, GroqLLM) and ui.api_key == KEY and ui.model == "ui-model" and ui.settings_from == "ui"
    assert ui.guarded is True  # the public provider address is checked like any other
    fallback = llm_from_settings({"provider": "groq"}, dotenv=dotenv)
    assert fallback.api_key == "env-key" and fallback.model == "env-model" and fallback.settings_from == "env"
    assert llm_from_settings({"provider": ""}, dotenv=dotenv) is None  # no console choice: server settings
    olla = llm_from_settings({"provider": "ollama", "model": "qwen2.5:7b", "base_url": "http://10.0.0.1"},
                             env={"LOGIMIND_OLLAMA_URL": "http://localhost:11434"}, dotenv=dotenv)
    assert olla.url == "http://localhost:11434" and olla.model == "qwen2.5:7b"  # a typed URL is never used for Ollama
    with pytest.raises(SettingsError):
        llm_from_settings({"provider": "openai", "base_url": "http://llm.example.com"}, dotenv=dotenv)


def test_chat_with_console_settings_keeps_the_invariants_and_never_returns_the_key(wired, caplog):
    caplog.set_level(logging.DEBUG)
    c, app, ha, hb, pid, use = wired

    def answer(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "ui-model"}]})
        intent = {"intent": {"action": "explain", "plan_id": pid}}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(intent)}}]})
    http = use(answer)
    h = headers(ha, provider="groq", model="ui-model", key=KEY)
    status = c.get("/api/copilot/status", headers=h)
    assert status.json()["provider"] == "groq" and status.json()["model"] == "ui-model" and KEY not in status.text
    r = c.post("/api/copilot/chat", json={"message": "explain the latest plan"}, headers=h)
    body = r.json()
    assert body["kind"] == "answer" and body["tool_calls"][0]["tool"] == "explain" and KEY not in r.text
    posts = [q for q in http.requests if q.method == "POST"]
    assert posts and all(q.headers["Authorization"] == f"Bearer {KEY}" for q in posts)
    assert all(str(q.url).startswith("https://api.groq.com/openai/v1/") for q in http.requests)
    assert KEY not in caplog.text
    with admin_session(app.state.db) as s:  # nothing about the key reached the audit log
        rows = s.scalars(select(AuditLog)).all()
        assert rows and not any(KEY in json.dumps({"a": r.action, "t": r.target, "d": r.detail}) for r in rows)
    # route fields from the model are still rejected: one retry, then the clarifying question
    use(lambda req: httpx.Response(200, json={"data": [{"id": "ui-model"}]}) if req.method == "GET" else
        httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
            {"intent": {"action": "solve", "plan_id": pid, "engine": "ortools", "routes": [[1, 2]]}})}}]}))
    r = c.post("/api/copilot/chat", json={"message": "use my routes"}, headers=h)
    assert r.json()["kind"] == "clarify" and r.json()["parse_attempts"] == 2


def test_console_settings_do_not_cross_tenants(wired):
    c, app, ha, hb, pid, use = wired
    use(lambda req: httpx.Response(200, json={"data": [{"id": "ui-model"}]}) if req.method == "GET" else
        httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
            {"intent": {"action": "explain", "plan_id": pid}})}}]}))
    r = c.post("/api/copilot/chat", json={"message": "explain plan A's plan"},
               headers=headers(hb, provider="groq", model="ui-model", key=KEY))
    out = r.json()  # tenant B names tenant A's plan through its own model settings: still not found
    assert out["kind"] == "clarify" and "can't find plan" in out["text"] and out["tool_calls"] == []
    # no settings header: tenant A gets the server's own model (the test's FakeLLM), not B's settings
    assert c.get("/api/copilot/status", headers=ha).json()["provider"] == "fake"
