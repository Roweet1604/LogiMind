"""Provider-agnostic LLM interface for the copilot (CLAUDE.md invariant 9: adapter + deterministic fake).

An LLM here does one thing: given a system prompt, the conversation and a JSON schema, return a JSON
string. The copilot validates it with Pydantic; the LLM's text is never shown as a result.

Providers (env LOGIMIND_LLM_PROVIDER):
* "ollama" (default): local Ollama through langchain-ollama, used only if the server answers and has the
  model (LOGIMIND_OLLAMA_URL, default http://localhost:11434; LOGIMIND_OLLAMA_MODEL, default llama3.2:3b).
* "groq" / "gemini" (optional hosted free tiers, decision 0032): plain httpx calls with schema-constrained JSON.
  GROQ_API_KEY + GROQ_MODEL / GEMINI_API_KEY + GEMINI_MODEL are read from the git-ignored backend/.env file,
  never from the API or the browser. The process environment is read too ONLY when LOGIMIND_LLM_KEYS_FROM_ENV=1
  (a host's secret store, e.g. the Hugging Face Space, decision 0046); a stray global variable is never picked up
  otherwise. The key is sent only in a request header, is hidden from repr and is scrubbed from every error message.
* "none": no model; the copilot says so.
* "scripted": ScriptedLLM, an offline demo stand-in with fixed rules, shown as "scripted · fake-scripted"
  (decision 0042). Not a language model; for demos without Ollama or a key.
* FakeLLM: deterministic, for tests (never selected by env).
"""
from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

import httpx

from app.copilot.netguard import MAX_RESPONSE_BYTES, BlockedURL, PinnedTransport, Resolver, check_base_url, check_public


@dataclass
class Availability:
    available: bool
    provider: str
    model: str | None
    reason: str = ""
    problem: str = ""  # short headline for the console, e.g. "Groq key missing or rejected"
    # "ready", "not_configured" (no provider, key or model set: nothing to try) or "unavailable" (set up, but the
    # check failed). Empty: derived from `available`. Decision 0046.
    state: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["state"] = self.state or ("ready" if self.available else "unavailable")
        return d


class LLM(Protocol):
    provider: str
    model: str | None

    def availability(self) -> Availability: ...

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        """Return one JSON document (as text) that should match `schema`."""


class LLMUnavailable(RuntimeError):
    pass


class LLMError(RuntimeError):
    """A hosted provider call failed. `kind`: auth, rate_limit, network, server, bad_request or bad_response.
    The message is plain language and never contains the key."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class FakeLLM:
    """Deterministic test double. `script` items are returned in order (str, dict -> JSON, or an Exception to
    raise); a callable `respond(system, messages)` can be used instead. Every call is recorded."""
    script: list[Any] = field(default_factory=list)
    respond: Callable[[str, list[dict[str, str]]], Any] | None = None
    provider: str = "fake"
    model: str | None = "fake-deterministic"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def availability(self) -> Availability:
        return Availability(True, self.provider, self.model, "deterministic fake for tests")

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "kind": "ok", "provider": self.provider, "model": self.model,
                "message": "Works: deterministic fake model (tests only)."}

    def list_models(self) -> list[str]:
        return [self.model] if self.model else []

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "schema": schema})
        out = self.respond(system, messages) if self.respond else (self.script.pop(0) if self.script else "{}")
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out)


_ORDINAL = {"first": 1, "one": 1, "second": 2, "two": 2, "third": 3, "three": 3, "fourth": 4, "four": 4,
            "fifth": 5, "five": 5}
_ENGINE_WORDS = (("hybrid", "hybrid"), ("ga", "ga"), ("genetic", "ga"), ("or-tools", "ortools"), ("ortools", "ortools"))


@dataclass
class ScriptedLLM:
    """Offline demo stand-in (LOGIMIND_LLM_PROVIDER=scripted, decision 0042): NOT a language model. Fixed rules
    turn a few phrasings into one intent (replan after a breakdown or failed delivery, solve, validate, explain,
    compare); anything else gets a clarify question that lists what it understands. Its output goes through the
    same schema validation, tools, solver, validator and confirmation as a real model's."""
    provider: str = "scripted"
    model: str | None = "fake-scripted"

    def availability(self) -> Availability:
        return Availability(True, self.provider, self.model,
                            "scripted demo stand-in, not a language model: it understands a few fixed phrasings")

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "kind": "ok", "provider": self.provider, "model": self.model,
                "message": "Works: scripted demo stand-in (fixed rules, not a language model)."}

    def list_models(self) -> list[str]:
        return [self.model] if self.model else []

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        user = [m["content"] for m in messages if m.get("role") == "user"
                and not m["content"].startswith("That output was invalid")]
        return json.dumps({"intent": self.intent_for(user[-1] if user else "", system)})

    @staticmethod
    def intent_for(text: str, system: str) -> dict[str, Any]:
        t = text.lower()
        listed = re.findall(r"^- (plan-[0-9a-f]{12}):", system, flags=re.M)  # newest first (agent.SYSTEM)
        named = re.findall(r"plan-[0-9a-f]{12}", t)
        plan = named[0] if named else (listed[0] if listed else None)
        understood = ("This scripted demo model understands, for example: \"Vehicle 0 broke down after its first "
                      "stop. Replan it.\", \"Customer 5 was not home, retry later.\", \"Validate the latest plan.\", "
                      "\"Explain the latest plan.\" or \"Solve the latest plan with GA.\"")
        if re.search(r"\b(edit|move|swap|reorder|assign)\b", t):
            return {"action": "refuse", "reason": "I never write or edit routes by hand; plans come only from the "
                                                  "solvers. I can replan after a disruption instead."}
        if plan is None:
            return {"action": "clarify", "question": "There are no plans yet. Create a plan first, then ask again."}
        steps = re.search(r"after (?:its |the )?(\w+) stops?", t)
        done = (int(steps.group(1)) if steps and steps.group(1).isdigit() else _ORDINAL.get(steps.group(1), 0)) \
            if steps else 0
        v = re.search(r"(?:vehicle|truck|van|route)\s*#?(\d+)", t)
        if v and re.search(r"broke|break|breakdown|down|failed vehicle|stuck", t):
            vehicle = int(v.group(1))
            return {"action": "reroute", "plan_id": plan, "engine": "ortools",
                    "event": {"type": "vehicle_breakdown", "vehicle": vehicle,
                              "completed": {str(vehicle): done} if done else {}}}
        c = re.search(r"customer\s*#?(\d+)", t)
        if c and re.search(r"fail|not home|nobody|refused|missed|could not deliver|couldn't deliver", t):
            retry = not re.search(r"drop|remove|cancel|do not retry|don't retry|no retry", t)
            return {"action": "reroute", "plan_id": plan, "engine": "ortools",
                    "event": {"type": "failed_delivery", "customer_id": int(c.group(1)), "retry": retry}}
        if "compare" in t:
            ids = named[:4] if len(named) >= 2 else listed[:2]
            if len(ids) >= 2:
                return {"action": "compare", "plan_ids": ids}
        if re.search(r"\b(validate|check|verify)\b", t):
            return {"action": "validate", "plan_id": plan}
        if re.search(r"\b(explain|why|summar)", t):
            return {"action": "explain", "plan_id": plan}
        if re.search(r"\b(solve|re-solve|resolve|optimi[sz]e|run)\b", t):
            engine = next((e for w, e in _ENGINE_WORDS if re.search(rf"\b{re.escape(w)}\b", t)), "ortools")
            return {"action": "solve", "plan_id": plan, "engine": engine}
        return {"action": "clarify", "question": understood}


@dataclass
class NoLLM:
    reason: str = "no LLM provider is configured (LOGIMIND_LLM_PROVIDER=none)"
    provider: str = "none"
    model: str | None = None

    configured: bool = False  # True: a provider was asked for but is unusable (e.g. an unknown name)

    def availability(self) -> Availability:
        return Availability(False, self.provider, None, self.reason,
                            state="unavailable" if self.configured else "not_configured")

    def complete_json(self, system, messages, schema) -> str:
        raise LLMUnavailable(self.reason)

    def test_connection(self) -> dict[str, Any]:
        return {"ok": False, "kind": "none", "provider": self.provider, "model": None, "message": self.reason}

    def list_models(self) -> list[str]:
        raise LLMError("none", self.reason)


@dataclass
class OllamaLLM:
    url: str = "http://localhost:11434"
    model: str | None = "llama3.2:3b"
    timeout_s: float = 120.0
    provider: str = "ollama"

    def availability(self) -> Availability:
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=2.0)
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
        except (httpx.HTTPError, ValueError) as exc:
            return Availability(False, self.provider, self.model,
                                f"no local model available: Ollama is not running at {self.url} "
                                f"({type(exc).__name__}); install Ollama and run `ollama pull {self.model}`")
        if self.model not in names and f"{self.model}:latest" not in names:
            return Availability(False, self.provider, self.model,
                                f"Ollama is running but model {self.model} is not installed; "
                                f"run `ollama pull {self.model}`")
        return Availability(True, self.provider, self.model, "local Ollama model")

    def test_connection(self) -> dict[str, Any]:
        av = self.availability()
        if av.available:
            return {"ok": True, "kind": "ok", "provider": self.provider, "model": self.model,
                    "message": f"Works: the local Ollama has the model {self.model}."}
        kind = "model" if "not installed" in av.reason else "network"
        msg = (f"Ollama is running, but the model {self.model} is not installed." if kind == "model"
               else f"Ollama is not reachable at {self.url}: it is not running on this computer.")
        return {"ok": False, "kind": kind, "provider": self.provider, "model": self.model, "message": msg}

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return chat_models([m.get("name") for m in r.json().get("models", []) if isinstance(m, dict)])
        except (httpx.HTTPError, ValueError, AttributeError):
            raise LLMError("network", f"Ollama is not reachable at {self.url}: it is not running on this computer."
                           ) from None

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        av = self.availability()
        if not av.available:
            raise LLMUnavailable(av.reason)
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama
        chat = ChatOllama(model=self.model, base_url=self.url, temperature=0, format=schema,
                          client_kwargs={"timeout": self.timeout_s})
        lc = [SystemMessage(system)] + [HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"])
                                        for m in messages]
        return str(chat.invoke(lc).content)


# ---- optional hosted providers (decision 0032) ------------------------------------------------------------
BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"
ENV_FILE = "backend\\.env"
SHORT = {"auth": "key missing or rejected", "rate_limit": "rate limit reached", "network": "not reachable",
         "server": "server problem", "bad_request": "request refused", "bad_response": "unusable answer",
         "model": "model not found", "blocked": "address not allowed"}
UI = "Copilot settings"  # where a key or model typed in the console is fixed
PROBE_TIMEOUT_S = 5.0  # the status check's model-list call; completions keep timeout_s (decision 0046)
KEYS_FROM_ENV = "LOGIMIND_LLM_KEYS_FROM_ENV"


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of backend/.env (# comments, optional quotes). A missing file gives {}."""
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def hosted_conf(dotenv: Path | None = None, env: Any = None) -> dict[str, str]:
    """Hosted providers' keys and models: backend/.env, plus the process environment only when
    LOGIMIND_LLM_KEYS_FROM_ENV=1 (a host's secret store; decision 0046). Then a non-empty environment value wins.
    Base-URL overrides (LOGIMIND_<P>_BASE_URL) come only from the file."""
    env = os.environ if env is None else env
    conf = read_dotenv(BACKEND_ENV if dotenv is None else dotenv)
    if env.get(KEYS_FROM_ENV, "") == "1":
        for prefix in ("GROQ", "GEMINI"):
            for name in (f"{prefix}_API_KEY", f"{prefix}_MODEL"):
                if env.get(name, "").strip():
                    conf[name] = env[name].strip()
    return conf


# Model ids that are not chat models (speech, embeddings, safety classifiers, images). "Load models" hides them.
NOT_CHAT = ("embed", "whisper", "tts", "guard", "moderation", "dall-e", "imagen", "image-generation", "transcri",
            "speech", "audio", "aqa", "rerank", "playai", "orpheus", "babbage", "davinci", "realtime", "computer-use",
            "search-preview", "codex", "sora", "turbo-instruct", "gpt-image")
# Automatic model choice (decision 0036): a model the provider marks as free first (OpenRouter ids end in ":free"),
# then these well-known chat models (they change over time; the list is a convenience, not a judgement), then the
# first chat model of the sorted list.
PREFERRED = {
    "groq": ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    "gemini": ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash"),
    "openai": ("gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4.1"),
}


def pick_model(kind: str, models: list[str]) -> tuple[str, str]:
    """(model, why) with why = "free", "preferred" or "first". `models` is a non-empty chat_models() list."""
    free = [m for m in models if m.endswith(":free")]
    if free:
        return free[0], "free"
    for name in PREFERRED.get(kind, ()):
        if name in models:
            return name, "preferred"
    return models[0], "first"
MAX_MODELS = 500


def chat_models(names: list[Any]) -> list[str]:
    """Clean, de-duplicated, sorted list of chat model ids (the first one is the automatic choice)."""
    ok = {n.strip() for n in names if isinstance(n, str) and 0 < len(n.strip()) <= 200 and n.isprintable()}
    return sorted(n for n in ok if not any(bad in n.lower() for bad in NOT_CHAT))[:MAX_MODELS]


def portable_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The intent schema without Pydantic's OpenAPI-only `discriminator` keyword (not JSON Schema)."""
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k != "discriminator"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return strip(copy.deepcopy(schema))


def _is_loopback_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class HostedLLM:
    """Shared plumbing for hosted providers: one httpx client per call, HTTP errors mapped to plain messages,
    a cached availability probe. Subclasses set the names and implement _headers, _probe and _complete."""
    model: str | None = None
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    timeout_s: float = 30.0
    transport: httpx.BaseTransport | None = field(default=None, repr=False)  # tests: httpx.MockTransport
    provider: str = ""
    label: str = ""
    key_var: str = ""
    model_var: str = ""
    # "env" (backend/.env), "host" (the host's secrets, LOGIMIND_LLM_KEYS_FROM_ENV=1, decision 0046) or "ui"
    # (Copilot settings in the console, decision 0033)
    settings_from: str = "env"
    guarded: bool = False  # True: the base URL is checked and pinned (netguard) before every call
    resolve: Resolver | None = field(default=None, repr=False)  # tests: a fake DNS
    auto_model: bool = False  # console settings without a model name: choose one from the provider's list
    chosen_automatically: bool = False
    choice_reason: str = ""  # "free", "preferred" or "first" (decision 0036)
    preference: str = ""  # which PREFERRED list applies; "" = the provider name
    _cache: tuple[float, Availability] | None = field(default=None, repr=False)

    def _scrub(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text

    def _where(self, var: str) -> str:
        if self.settings_from == "ui":
            return UI
        return f"the {var} secret or variable" if self.settings_from == "host" else f"{var} in {ENV_FILE}"

    def _setup_problem(self) -> Availability | None:
        if not self.api_key:
            why = {"ui": "no key in Copilot settings", "host": f"the {self.key_var} secret is not set on this server"
                   }.get(self.settings_from, f"{self.key_var} is empty in {ENV_FILE}")
            return Availability(False, self.provider, self.model or None,
                                f"{self.label} key missing or rejected: {why}", f"{self.label} key missing or rejected",
                                state="not_configured")
        if not self.model and not self.auto_model:
            return Availability(False, self.provider, None,
                                f"{self.label} model not set: put a model name in {self._where(self.model_var)}",
                                f"{self.label} model not set", state="not_configured")
        return None

    def test_connection(self) -> dict[str, Any]:
        """One minimal call (the model list or the model itself, never a completion). Only success or a plain
        error comes back; never the key."""
        bad = self._setup_problem()
        if bad:
            kind = "auth" if not self.api_key else "model"
            return {"ok": False, "kind": kind, "provider": self.provider, "model": self.model, "message": bad.reason}
        try:
            self._choose_model()
            if not self.chosen_automatically:
                self._probe()
        except LLMError as exc:
            return {"ok": False, "kind": exc.kind, "provider": self.provider, "model": self.model,
                    "message": self._scrub(str(exc))}
        return {"ok": True, "kind": "ok", "provider": self.provider, "model": self.model,
                "chosen_automatically": self.chosen_automatically, "message": self._works()}

    def _works(self) -> str:
        if self.chosen_automatically:
            why = {"free": "a free model", "preferred": "a common chat model",
                   "first": "the first chat model in its list"}[self.choice_reason]
            return f"Works: {self.label} is ready, using {self.model} (chosen automatically: {why})."
        return f"Works: {self.label} is ready, using {self.model}."

    def _choose_model(self, timeout: float | None = None) -> None:
        """Console settings without a model name: choose one from the provider's list (pick_model)."""
        if self.model or not self.auto_model:
            return
        models = self.list_models(timeout)
        if not models:
            raise LLMError("model", f"{self.label} lists no chat models for this key; type a model name in {UI}.")
        self.model, self.choice_reason = pick_model(self.preference or self.provider, models)
        self.chosen_automatically = True

    def list_models(self, timeout: float | None = None) -> list[str]:
        """The provider's chat models (one list call through the same guard and limits). Never needs a model."""
        if not self.api_key:
            raise LLMError("auth", self._setup_problem().reason)
        return chat_models(self._list_raw(timeout))

    def _list_raw(self, timeout: float | None = None) -> list[Any]:
        raise NotImplementedError

    def availability(self) -> Availability:
        bad = self._setup_problem()
        if bad:
            return bad
        now = time.monotonic()
        if self._cache and now < self._cache[0]:
            return self._cache[1]
        try:  # a short timeout: the status check must answer quickly (decision 0046)
            self._choose_model(PROBE_TIMEOUT_S)
            if not self.chosen_automatically:
                self._probe(PROBE_TIMEOUT_S)
            how = "chosen automatically: the first chat model in its list" if self.chosen_automatically else \
                "optional free tier"
            av = Availability(True, self.provider, self.model, f"hosted {self.label} model ({how})")
            if self.chosen_automatically:
                av.reason = f"hosted {self.label} model (chosen automatically: {self.choice_reason})"
        except LLMError as exc:
            av = Availability(False, self.provider, self.model, str(exc), f"{self.label} {SHORT[exc.kind]}")
        self._cache = (now + (300.0 if av.available else 30.0), av)
        return av

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        bad = self._setup_problem()
        if bad:
            raise LLMUnavailable(bad.reason)
        try:
            self._choose_model()
            return self._complete(system, messages, portable_schema(schema))
        except LLMError as exc:
            if exc.kind == "auth":  # show the rejected key in the status at once, not after the cache expires
                self._cache = (time.monotonic() + 30.0, Availability(False, self.provider, self.model, str(exc),
                                                                     f"{self.label} key missing or rejected"))
            raise

    # ---- HTTP -----------------------------------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _request(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        timeout = self.timeout_s if timeout is None else min(timeout, self.timeout_s)
        transport = self.transport
        if self.guarded:
            try:
                host, port = check_base_url(self.base_url)
                pinned_ip = check_public(host, port, self.resolve)
            except BlockedURL as exc:
                raise LLMError("blocked", f"{self.label}: {exc}.") from None
            transport = transport or PinnedTransport({host: pinned_ip})
        try:
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
                              transport=transport, follow_redirects=False) as client:
                with client.stream(method, path, json=body, headers=self._headers()) as streamed:
                    raw = b""
                    for chunk in streamed.iter_bytes():
                        raw += chunk
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise LLMError("bad_response", f"{self.label} sent an answer larger than 1 MB; it was "
                                                           "not read.")
                    r = httpx.Response(streamed.status_code, headers=streamed.headers, content=raw)
        except httpx.TimeoutException:
            raise LLMError("network", f"{self.label} did not answer within {timeout:g} s (network timeout). "
                                      "Check the internet connection and try again.") from None
        except httpx.TransportError as exc:
            raise LLMError("network", f"{self.label} could not be reached from the LogiMind server "
                                      f"({type(exc).__name__}); check the internet connection or try again later."
                           ) from None
        if 300 <= r.status_code < 400:
            raise LLMError("bad_request", f"{self.label} answered with a redirect (HTTP {r.status_code}); redirects "
                                          "are not followed. Check the base URL.")
        if r.is_success:
            try:
                return r.json()
            except ValueError:
                raise LLMError("bad_response", f"{self.label} sent an answer that is not JSON.") from None
        raise self._error_for(r)

    def _error_for(self, r: httpx.Response) -> LLMError:
        try:
            err = r.json().get("error", {})
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        except (ValueError, AttributeError):
            detail = ""
        detail = self._scrub(detail)[:200]
        code = r.status_code
        if code in (401, 403) or (code == 400 and ("API_KEY_INVALID" in r.text or "API key not valid" in r.text)):
            if self.settings_from == "ui":  # one plain sentence for a key pasted in the console (decision 0036)
                return LLMError("auth", f"{self.label} rejected this key. Check that the whole key was copied, "
                                        "with no spaces or quotes.")
            if self.settings_from == "host":
                return LLMError("auth", f"{self.label} key missing or rejected (HTTP {code}). Check the "
                                        f"{self.key_var} secret and restart the server.")
            return LLMError("auth", f"{self.label} key missing or rejected (HTTP {code}). Check {self.key_var} in "
                                    f"{ENV_FILE} and restart the server.")
        if code == 429:
            wait = r.headers.get("retry-after")
            return LLMError("rate_limit", f"{self.label} rate limit reached (HTTP 429)"
                                          + (f"; try again in {wait} s" if wait else "; try again in a minute")
                                          + ", because free tiers allow only a few requests per minute.")
        if code == 404:
            return LLMError("model", f"{self.label}: model {self.model!r} not found (HTTP 404). "
                                     f"Check the model name in {self._where(self.model_var)}.")
        if code >= 500:
            return LLMError("server", f"{self.label} had a server problem (HTTP {code}). Try again later.")
        return LLMError("bad_request", f"{self.label} refused the request (HTTP {code})"
                                       + (f": {detail}" if detail else "") + ".")

    def _probe(self, timeout: float | None = None) -> None:
        raise NotImplementedError

    def _complete(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        raise NotImplementedError


@dataclass
class OpenAICompatLLM(HostedLLM):
    """Any OpenAI-compatible chat API (base URL from Copilot settings, always guarded) with `response_format`
    json_schema. Paid services charge for every call."""
    provider: str = "openai"
    label: str = "OpenAI-compatible service"
    key_var: str = "key"
    model_var: str = "model"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _list_raw(self, timeout: float | None = None) -> list[Any]:
        return [m.get("id") for m in (self._request("GET", "/models", timeout=timeout).get("data") or [])
                if isinstance(m, dict)]

    def _probe(self, timeout: float | None = None) -> None:
        ids = set(self._list_raw(timeout))
        if self.model not in ids:
            raise LLMError("model", f"{self.label}: model {self.model!r} not found in its model list. "
                                    f"Check the model name in {self._where(self.model_var)}.")

    def _complete(self, system, messages, schema):
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "system", "content": system}] + [dict(m) for m in messages],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "intent_envelope", "schema": schema}}}
        data = self._request("POST", "/chat/completions", body)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise LLMError("bad_response", f"{self.label} returned no answer.") from None


@dataclass
class GroqLLM(OpenAICompatLLM):
    """Groq's OpenAI-compatible API with `response_format` json_schema (structured outputs)."""
    base_url: str = "https://api.groq.com/openai/v1"
    provider: str = "groq"
    label: str = "Groq"
    key_var: str = "GROQ_API_KEY"
    model_var: str = "GROQ_MODEL"


@dataclass
class GeminiLLM(HostedLLM):
    """Gemini API generateContent with responseMimeType application/json and responseJsonSchema. The key goes in
    the x-goog-api-key header, never in the URL (URLs end up in logs)."""
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    provider: str = "gemini"
    label: str = "Gemini"
    key_var: str = "GEMINI_API_KEY"
    model_var: str = "GEMINI_MODEL"

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key}

    def _probe(self, timeout: float | None = None) -> None:
        self._request("GET", f"/models/{self.model}", timeout=timeout)

    def _list_raw(self, timeout: float | None = None) -> list[Any]:
        """Models that can generate content; ids without the "models/" prefix. The key stays in the header."""
        out = []
        for m in self._request("GET", "/models?pageSize=1000", timeout=timeout).get("models") or []:
            if isinstance(m, dict) and "generateContent" in (m.get("supportedGenerationMethods") or []):
                out.append(str(m.get("name", "")).removeprefix("models/"))
        return out

    def _complete(self, system, messages, schema):
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                             for m in messages],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                     "responseJsonSchema": schema}}
        data = self._request("POST", f"/models/{self.model}:generateContent", body)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            first = (data.get("candidates") or [{}])[0] if isinstance(data.get("candidates"), list) else {}
            why = (data.get("promptFeedback") or {}).get("blockReason") or first.get("finishReason")
            raise LLMError("bad_response", "Gemini returned no answer" + (f" ({why})" if why else "") + ".") from None


HOSTED: dict[str, tuple[type[HostedLLM], str]] = {"groq": (GroqLLM, "GROQ"), "gemini": (GeminiLLM, "GEMINI")}


def llm_from_env(env: dict[str, str] | None = None, dotenv: Path | None = None) -> LLM:
    """The provider name comes from LOGIMIND_LLM_PROVIDER (start-dev.bat copies backend/.env into the process).
    Hosted providers' keys and models come from the backend/.env FILE, or from the environment when
    LOGIMIND_LLM_KEYS_FROM_ENV=1 (hosted_conf); base URLs only from the file."""
    env = os.environ if env is None else env
    provider = env.get("LOGIMIND_LLM_PROVIDER", "ollama").strip().lower()
    if provider == "none":
        return NoLLM()
    if provider == "scripted":
        return ScriptedLLM()
    if provider == "ollama":
        return OllamaLLM(url=env.get("LOGIMIND_OLLAMA_URL", "http://localhost:11434"),
                         model=env.get("LOGIMIND_OLLAMA_MODEL", "llama3.2:3b"))
    if provider in HOSTED:
        cls, prefix = HOSTED[provider]
        conf = hosted_conf(dotenv, env)
        llm = cls(model=conf.get(f"{prefix}_MODEL", ""), api_key=conf.get(f"{prefix}_API_KEY", ""),
                  settings_from="host" if env.get(KEYS_FROM_ENV, "") == "1" else "env")
        base = conf.get(f"LOGIMIND_{prefix}_BASE_URL", "")
        if base:  # only for a local fake server (tests, the browser check): a key must never go anywhere else
            if not _is_loopback_url(base):
                return NoLLM(reason=f"LOGIMIND_{prefix}_BASE_URL may only point to this computer (localhost); "
                                    "it was ignored so the key is not sent anywhere else", provider=provider,
                         configured=True)
            llm.base_url = base.rstrip("/")
        return llm
    return NoLLM(reason=f"unknown LOGIMIND_LLM_PROVIDER {provider!r}; expected ollama, groq, gemini, scripted or none",
                 configured=True)


# ---- settings typed in the console (decision 0033) ----------------------------------------------------------
UI_PROVIDERS = ("ollama", "groq", "gemini", "openai", "openrouter")
# OpenAI-compatible services the console detects from the key prefix (decision 0036). Any other base URL is a generic
# "OpenAI-compatible service". The operator may point these at a local fake in backend/.env (localhost only).
OPENAI_LIKE = {"openai": ("https://api.openai.com/v1", "OpenAI", "LOGIMIND_OPENAI_BASE_URL"),
               "openrouter": ("https://openrouter.ai/api/v1", "OpenRouter", "LOGIMIND_OPENROUTER_BASE_URL")}
LABEL_BY_HOST = {"api.openai.com": ("OpenAI", "openai"), "openrouter.ai": ("OpenRouter", "openrouter")}


class SettingsError(ValueError):
    """Copilot settings from the console are not usable. Plain message; never contains the key."""


def llm_from_settings(s: dict[str, str], env: dict[str, str] | None = None, dotenv: Path | None = None,
                      transport: httpx.BaseTransport | None = None, resolve: Resolver | None = None) -> LLM | None:
    """Build the LLM for ONE request from the console's settings (provider, model, key, base_url). None when the
    console chose no provider (the server's own settings apply). Fields the console leaves empty fall back to
    backend/.env. Nothing here is stored."""
    provider = s.get("provider", "").strip().lower()
    if not provider:
        return None
    if provider == "anthropic":
        raise SettingsError("Anthropic keys are not supported yet: LogiMind has no Anthropic adapter")
    if provider not in UI_PROVIDERS:
        raise SettingsError("unknown provider; choose Ollama (local), Groq, Gemini, OpenRouter or OpenAI-compatible")
    env = os.environ if env is None else env
    model, key = s.get("model", "").strip(), s.get("key", "").strip()
    if provider == "ollama":  # always the server's own local Ollama URL: plain http only ever goes there
        return OllamaLLM(url=env.get("LOGIMIND_OLLAMA_URL", "http://localhost:11434"),
                         model=model or env.get("LOGIMIND_OLLAMA_MODEL", "llama3.2:3b"))
    if provider in OPENAI_LIKE:
        default, label, override_var = OPENAI_LIKE[provider]
        base = s.get("base_url", "").strip().rstrip("/")
        override = read_dotenv(BACKEND_ENV if dotenv is None else dotenv).get(override_var, "")
        if not base and override and _is_loopback_url(override):  # operator's local fake (decision 0036)
            return OpenAICompatLLM(model=model, api_key=key, base_url=override.rstrip("/"), settings_from="ui",
                                   label=label, preference=provider, provider=provider, transport=transport,
                                   resolve=resolve, auto_model=not model)
        base = base or default
        try:
            host, _port = check_base_url(base)
        except BlockedURL as exc:
            raise SettingsError(f"OpenAI-compatible base URL: {exc}") from None
        label, kind = LABEL_BY_HOST.get(host, ("OpenAI-compatible service", "openai"))
        return OpenAICompatLLM(model=model, api_key=key, base_url=base, settings_from="ui", guarded=True,
                               label=label, preference=kind, provider=kind, transport=transport, resolve=resolve,
                               auto_model=not model)
    cls, prefix = HOSTED[provider]
    conf = hosted_conf(dotenv, env)
    server = "host" if env.get(KEYS_FROM_ENV, "") == "1" else "env"
    llm = cls(model=model or conf.get(f"{prefix}_MODEL", ""), api_key=key or conf.get(f"{prefix}_API_KEY", ""),
              settings_from="ui" if key else server, transport=transport, resolve=resolve)
    llm.auto_model = not llm.model  # chosen in the console without a model name: first chat model in the list
    override = conf.get(f"LOGIMIND_{prefix}_BASE_URL", "")
    if override and _is_loopback_url(override):  # operator's own setting in backend/.env (decision 0032)
        llm.base_url = override.rstrip("/")
    else:  # the provider's public address: checked and pinned like any other outbound call
        llm.guarded = True
    return llm
