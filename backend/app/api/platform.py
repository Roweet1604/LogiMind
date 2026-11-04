"""Tenant platform endpoints (P6d): webhook endpoints, their delivery records, and the audit log."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import require_principal
from app.db.keys import Principal
from app.db.models import AuditLog, Webhook, WebhookDelivery
from app.db.session import tenant_session
from app.services.notify import EVENTS, WebhookURLError, check_webhook_url, new_secret, new_webhook_id
from app.services.plans import audit

router = APIRouter(prefix="/api", tags=["platform"])
Event = Literal["plan.completed", "plan.failed", "plan.replanned"]
assert set(Event.__args__) == set(EVENTS)


class WebhookIn(BaseModel):
    url: str = Field(max_length=2000)
    events: list[Event] = Field(default_factory=lambda: list(EVENTS), min_length=1)


def _view(h: Webhook) -> dict:
    return {"webhook_id": h.id, "url": h.url, "events": h.events, "active": h.active,
            "created_at": h.created_at.isoformat() if h.created_at else None}


@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookIn, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Register an endpoint. The signing `secret` is returned ONCE; verify each delivery's
    `LogiMind-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>." + body>` with it."""
    try:
        check_webhook_url(body.url)
    except WebhookURLError as exc:
        raise HTTPException(422, detail=str(exc))
    hook = Webhook(id=new_webhook_id(), tenant_id=who.tenant_id, url=body.url, secret=new_secret(),
                   events=sorted(set(body.events)), active=True)
    with tenant_session(request.app.state.db, who.tenant_id) as s:
        s.add(hook)
        audit(s, who.tenant_id, who.key_id, "webhook.create", hook.id, url=body.url, events=hook.events)
        s.commit()
        return {**_view(hook), "secret": hook.secret}


@router.get("/webhooks")
def list_webhooks(request: Request, who: Principal = Depends(require_principal)) -> list[dict]:
    with tenant_session(request.app.state.db, who.tenant_id) as s:
        return [_view(h) for h in s.scalars(select(Webhook).order_by(Webhook.created_at))]


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Deactivates the endpoint (kept for the delivery history)."""
    with tenant_session(request.app.state.db, who.tenant_id) as s:
        hook = s.get(Webhook, webhook_id)
        if hook is None:
            raise HTTPException(404, detail=f"webhook {webhook_id} not found")
        hook.active = False
        audit(s, who.tenant_id, who.key_id, "webhook.deactivate", webhook_id)
        s.commit()
        return _view(hook)


@router.get("/webhooks/{webhook_id}/deliveries")
def list_deliveries(webhook_id: str, request: Request, who: Principal = Depends(require_principal)) -> list[dict]:
    with tenant_session(request.app.state.db, who.tenant_id) as s:
        if s.get(Webhook, webhook_id) is None:
            raise HTTPException(404, detail=f"webhook {webhook_id} not found")
        rows = s.scalars(select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
                         .order_by(WebhookDelivery.id))
        return [{"event": d.event, "plan_id": d.target, "delivered": d.delivered, "attempts": d.attempts,
                 "last_status": d.last_status, "errors": d.errors or [], "at": d.at.isoformat() if d.at else None}
                for d in rows]


@router.get("/audit")
def list_audit(request: Request, limit: int = 100, who: Principal = Depends(require_principal)) -> list[dict]:
    """The caller's tenant audit log, newest first."""
    limit = max(1, min(limit, 1000))
    with tenant_session(request.app.state.db, who.tenant_id) as s:
        rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
        return [{"id": a.id, "actor": a.actor, "action": a.action, "target": a.target, "detail": a.detail,
                 "at": a.at.isoformat() if a.at else None} for a in rows]
