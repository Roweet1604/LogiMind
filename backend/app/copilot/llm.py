"""Provider-agnostic LLM interface for the copilot (CLAUDE.md invariant 9: adapter + deterministic fake).

An LLM here does one thing: given a system prompt, the conversation and a JSON schema, return a JSON
string. The copilot validates it with Pydantic; the LLM's text is never shown as a result.

Providers (env LOGIMIND_LLM_PROVIDER):
* "ollama" (default): local Ollama through langchain-ollama, used only if the server answers and has the
  model (LOGIMIND_OLLAMA_URL, default http://localhost:11434; LOGIMIND_OLLAMA_MODEL, default llama3.2:3b).
* "none": no model; the copilot says so.
* FakeLLM: deterministic, for tests (never selected by env).
Nothing here calls a paid or key-gated service.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx


@dataclass
class Availability:
    available: bool
    provider: str
    model: str | None
    reason: str = ""

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


def llm_from_env() -> LLM:
    provider = os.environ.get("LOGIMIND_LLM_PROVIDER", "ollama").lower()
    if provider == "none":
        return NoLLM()
    if provider == "ollama":
        return OllamaLLM(url=os.environ.get("LOGIMIND_OLLAMA_URL", "http://localhost:11434"),
                         model=os.environ.get("LOGIMIND_OLLAMA_MODEL", "llama3.2:3b"))
    return NoLLM(reason=f"unknown LOGIMIND_LLM_PROVIDER {provider!r}; expected ollama or none")
