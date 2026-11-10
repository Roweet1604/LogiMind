"""Provider-agnostic LLM interface for the copilot (CLAUDE.md invariant 9: adapter + deterministic fake).

An LLM here does one thing: given a system prompt, the conversation and a JSON schema, return a JSON
string. The copilot validates it with Pydantic; the LLM's text is never shown as a result.

Providers (env LOGIMIND_LLM_PROVIDER):
* "ollama" (default): local Ollama through langchain-ollama, used only if the server answers and has the
  model (LOGIMIND_OLLAMA_URL, default http://localhost:11434; LOGIMIND_OLLAMA_MODEL, default llama3.2:3b).
* "groq" / "gemini" (optional hosted free tiers, decision 0032): plain httpx calls with schema-constrained JSON.
  GROQ_API_KEY + GROQ_MODEL / GEMINI_API_KEY + GEMINI_MODEL are read ONLY from the git-ignored backend/.env
  file, never from the global environment, the API or the browser. The key is sent only in a request header,
  is hidden from repr and is scrubbed from every error message.
* "none": no model; the copilot says so.
* FakeLLM: deterministic, for tests (never selected by env).
"""
from __future__ import annotations

import copy
import ipaddress
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

import httpx


@dataclass
class Availability:
    available: bool
    provider: str
    model: str | None
    reason: str = ""
    problem: str = ""  # short headline for the console, e.g. "Groq key missing or rejected"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


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

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "schema": schema})
        out = self.respond(system, messages) if self.respond else (self.script.pop(0) if self.script else "{}")
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out)


@dataclass
class NoLLM:
    reason: str = "no LLM provider is configured (LOGIMIND_LLM_PROVIDER=none)"
    provider: str = "none"
    model: str | None = None

    def availability(self) -> Availability:
        return Availability(False, self.provider, None, self.reason)

    def complete_json(self, system, messages, schema) -> str:
        raise LLMUnavailable(self.reason)


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
         "server": "server problem", "bad_request": "request refused", "bad_response": "unusable answer"}


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
    _cache: tuple[float, Availability] | None = field(default=None, repr=False)

    def _scrub(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text

    def _setup_problem(self) -> Availability | None:
        if not self.api_key:
            return Availability(False, self.provider, self.model or None,
                                f"{self.label} key missing or rejected: {self.key_var} is empty in {ENV_FILE}",
                                f"{self.label} key missing or rejected")
        if not self.model:
            return Availability(False, self.provider, None,
                                f"{self.label} model not set: put a model name in {self.model_var} in {ENV_FILE}",
                                f"{self.label} model not set")
        return None

    def availability(self) -> Availability:
        bad = self._setup_problem()
        if bad:
            return bad
        now = time.monotonic()
        if self._cache and now < self._cache[0]:
            return self._cache[1]
        try:
            self._probe()
            av = Availability(True, self.provider, self.model, f"hosted {self.label} model (optional free tier)")
        except LLMError as exc:
            av = Availability(False, self.provider, self.model, str(exc), f"{self.label} {SHORT[exc.kind]}")
        self._cache = (now + (300.0 if av.available else 30.0), av)
        return av

    def complete_json(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        bad = self._setup_problem()
        if bad:
            raise LLMUnavailable(bad.reason)
        try:
            return self._complete(system, messages, portable_schema(schema))
        except LLMError as exc:
            if exc.kind == "auth":  # show the rejected key in the status at once, not after the cache expires
                self._cache = (time.monotonic() + 30.0, Availability(False, self.provider, self.model, str(exc),
                                                                     f"{self.label} key missing or rejected"))
            raise

    # ---- HTTP -----------------------------------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_s, transport=self.transport) as client:
                r = client.request(method, path, json=body, headers=self._headers())
        except httpx.TimeoutException:
            raise LLMError("network", f"{self.label} did not answer within {self.timeout_s:g} s (network timeout). "
                                      "Check the internet connection and try again.") from None
        except httpx.TransportError as exc:
            raise LLMError("network", f"{self.label} could not be reached ({type(exc).__name__}). Check the "
                                      "internet connection and try again.") from None
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
            return LLMError("auth", f"{self.label} key missing or rejected (HTTP {code}). Check {self.key_var} in "
                                    f"{ENV_FILE} and restart the server.")
        if code == 429:
            wait = r.headers.get("retry-after")
            return LLMError("rate_limit", f"{self.label} rate limit reached (HTTP 429)"
                                          + (f"; try again in {wait} s" if wait else "; try again in a minute")
                                          + ". Free tiers allow only a few requests per minute.")
        if code == 404:
            return LLMError("bad_request", f"{self.label} does not know the model {self.model!r} (HTTP 404). "
                                           f"Check {self.model_var} in {ENV_FILE}.")
        if code >= 500:
            return LLMError("server", f"{self.label} had a server problem (HTTP {code}). Try again later.")
        return LLMError("bad_request", f"{self.label} refused the request (HTTP {code})"
                                       + (f": {detail}" if detail else "") + ".")

    def _probe(self) -> None:
        raise NotImplementedError

    def _complete(self, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        raise NotImplementedError


@dataclass
class GroqLLM(HostedLLM):
    """Groq's OpenAI-compatible API with `response_format` json_schema (structured outputs)."""
    base_url: str = "https://api.groq.com/openai/v1"
    provider: str = "groq"
    label: str = "Groq"
    key_var: str = "GROQ_API_KEY"
    model_var: str = "GROQ_MODEL"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _probe(self) -> None:
        ids = {m.get("id") for m in self._request("GET", "/models").get("data", [])}
        if self.model not in ids:
            raise LLMError("bad_request", f"Groq does not offer the model {self.model!r}. "
                                          f"Check {self.model_var} in {ENV_FILE}.")

    def _complete(self, system, messages, schema):
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "system", "content": system}] + [dict(m) for m in messages],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "intent_envelope", "schema": schema}}}
        data = self._request("POST", "/chat/completions", body)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise LLMError("bad_response", "Groq returned no answer.") from None


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

    def _probe(self) -> None:
        self._request("GET", f"/models/{self.model}")

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
    Hosted providers' keys, models and base URLs are read from the backend/.env FILE only."""
    env = os.environ if env is None else env
    provider = env.get("LOGIMIND_LLM_PROVIDER", "ollama").strip().lower()
    if provider == "none":
        return NoLLM()
    if provider == "ollama":
        return OllamaLLM(url=env.get("LOGIMIND_OLLAMA_URL", "http://localhost:11434"),
                         model=env.get("LOGIMIND_OLLAMA_MODEL", "llama3.2:3b"))
    if provider in HOSTED:
        cls, prefix = HOSTED[provider]
        conf = read_dotenv(BACKEND_ENV if dotenv is None else dotenv)
        llm = cls(model=conf.get(f"{prefix}_MODEL", ""), api_key=conf.get(f"{prefix}_API_KEY", ""))
        base = conf.get(f"LOGIMIND_{prefix}_BASE_URL", "")
        if base:  # only for a local fake server (tests, the browser check): a key must never go anywhere else
            if not _is_loopback_url(base):
                return NoLLM(reason=f"LOGIMIND_{prefix}_BASE_URL may only point to this computer (localhost); "
                                    "it was ignored so the key is not sent anywhere else", provider=provider)
            llm.base_url = base.rstrip("/")
        return llm
    return NoLLM(reason=f"unknown LOGIMIND_LLM_PROVIDER {provider!r}; expected ollama, groq, gemini or none")
