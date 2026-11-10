"""Copilot endpoints (P8). Tenant-scoped; the copilot acts only through the tenant's own plans.

Copilot settings from the console (decision 0033) come with each request as headers: X-LLM-Provider, X-LLM-Model,
X-LLM-Base-URL and X-LLM-Key. They are read by hand, not declared as typed parameters, because a validation error
would repeat the value (the key) in its reply. Nothing from them is stored, logged, audited or returned.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import require_principal
from app.copilot.llm import LLM, SettingsError, llm_from_settings
from app.db.keys import Principal

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

SETTINGS_HEADERS = {"provider": ("x-llm-provider", 20, "provider"), "model": ("x-llm-model", 200, "model name"),
                    "base_url": ("x-llm-base-url", 500, "base URL"), "key": ("x-llm-key", 512, "key")}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(None, max_length=40)


class ConfirmIn(BaseModel):
    session_id: str = Field(max_length=40)
    pending_id: str = Field(max_length=40)
    approve: bool


def llm_for(request: Request) -> LLM | None:
    """This request's model from the console's settings, or None (the server's own settings)."""
    s: dict[str, str] = {}
    for name, (header, limit, label) in SETTINGS_HEADERS.items():
        value = request.headers.get(header, "")
        if len(value) > limit or any(not 32 <= ord(c) <= 126 for c in value):
            raise HTTPException(400, detail=f"Copilot settings: the {label} is too long or contains characters "
                                            "that are not allowed.")
        s[name] = value
    try:
        # The three app.state hooks are for tests only (fake HTTP layer, fake DNS, a temporary .env file).
        return llm_from_settings(s, dotenv=getattr(request.app.state, "llm_dotenv", None),
                                 transport=getattr(request.app.state, "llm_transport", None),
                                 resolve=getattr(request.app.state, "llm_resolve", None))
    except SettingsError as exc:
        raise HTTPException(400, detail=f"Copilot settings: {exc}.") from None


@router.get("/status")
def copilot_status(request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Which provider and model the copilot uses for this request, and whether it is available. Never the key."""
    return request.app.state.copilot.status(llm_for(request))


@router.post("/test")
def copilot_test(request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Test the provider settings with one minimal call (the model list, never a completion). Returns only success
    or a plain-language error (kind: ok, auth, model, rate_limit, network, blocked, server, bad_request, ...)."""
    return request.app.state.copilot.test_connection(llm_for(request))


@router.post("/models")
def copilot_models(request: Request, who: Principal = Depends(require_principal)) -> dict:
    """The provider's chat models for the console's "Load models": one list call with the same key header, guard and
    limits as every other call. Returns names only, or a plain error; never the key."""
    return request.app.state.copilot.list_models(llm_for(request))


@router.post("/chat")
def copilot_chat(body: ChatIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """One message. Reply kinds: answer, clarify, confirm (needs POST /confirm), refuse, error, unavailable.
    Answers are built only from tool outputs, listed in `tool_calls`."""
    return request.app.state.copilot.chat(who, body.message, body.session_id, llm=llm_for(request))


@router.post("/confirm")
def copilot_confirm(body: ConfirmIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Approve or cancel a pending change to an active plan (a reroute)."""
    return request.app.state.copilot.confirm(who, body.session_id, body.pending_id, body.approve)
