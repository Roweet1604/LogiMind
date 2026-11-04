"""Copilot endpoints (P8). Tenant-scoped; the copilot acts only through the tenant's own plans."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.auth import require_principal
from app.db.keys import Principal

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(None, max_length=40)


class ConfirmIn(BaseModel):
    session_id: str = Field(max_length=40)
    pending_id: str = Field(max_length=40)
    approve: bool


@router.get("/status")
def copilot_status(request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Whether a local model is available. With none, the console says so plainly."""
    return request.app.state.copilot.status()


@router.post("/chat")
def copilot_chat(body: ChatIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """One message. Reply kinds: answer, clarify, confirm (needs POST /confirm), refuse, error, unavailable.
    Answers are built only from tool outputs, listed in `tool_calls`."""
    return request.app.state.copilot.chat(who, body.message, body.session_id)


@router.post("/confirm")
def copilot_confirm(body: ConfirmIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Approve or cancel a pending change to an active plan (a reroute)."""
    return request.app.state.copilot.confirm(who, body.session_id, body.pending_id, body.approve)
