"""Tenant webhook notifications (P6d): which endpoints get an event, delivery off the solver thread,
and a stored delivery record + audit row for every attempt series.

Deliveries run on their own small thread pool, so retries and back-off never delay solver jobs.
The sender is an adapter (`HttpxSender` in the app, `FakeSender` in tests), so tests run offline.
"""
from __future__ import annotations

import ipaddress
import os
import secrets
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditLog, Webhook, WebhookDelivery
from app.db.session import tenant_session
from app.services.webhooks import DEFAULT_BACKOFF_S, WebhookSender, deliver

EVENTS = ("plan.completed", "plan.failed", "plan.replanned")


class WebhookURLError(ValueError):
    pass


def check_webhook_url(url: str) -> None:
    """http(s) only, with a host. Loopback/private/link-local literal addresses and `localhost` are refused
    (basic SSRF guard) unless LOGIMIND_WEBHOOK_ALLOW_PRIVATE=1 (dev only, off by default). Host names are
    not resolved here, so a public name pointing at a private address is not caught (decision 0010)."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise WebhookURLError("webhook url must be http(s)://host/...")
    if os.environ.get("LOGIMIND_WEBHOOK_ALLOW_PRIVATE") == "1":
        return
    host = u.hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise WebhookURLError("webhook url must not point at localhost")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
        raise WebhookURLError("webhook url must not point at a private, loopback or reserved address")


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def new_webhook_id() -> str:
    return f"wh-{uuid.uuid4().hex[:12]}"


class WebhookNotifier:
    def __init__(self, factory: sessionmaker[Session], sender: WebhookSender,
                 backoff_s: tuple[float, ...] = DEFAULT_BACKOFF_S, workers: int = 2):
        self.factory = factory
        self.sender = sender
        self.backoff_s = backoff_s
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="webhook")
        self._futures: list[Future] = []
        self._lock = threading.Lock()

    def emit(self, tenant_id: str, event: str, target: str, payload: dict[str, Any]) -> int:
        """Queue `event` for every active endpoint of this tenant that subscribed to it. Returns the count."""
        with tenant_session(self.factory, tenant_id) as s:
            hooks = [(h.id, h.url, h.secret) for h in s.scalars(select(Webhook).where(Webhook.active.is_(True)))
                     if event in (h.events or [])]
        for hook in hooks:
            fut = self.pool.submit(self._deliver_one, tenant_id, *hook, event, target, payload)
            with self._lock:
                self._futures.append(fut)
        return len(hooks)

    def _deliver_one(self, tenant_id: str, hook_id: str, url: str, secret: str, event: str, target: str,
                     payload: dict[str, Any]) -> None:
        res = deliver(self.sender, url, secret, event, payload, backoff_s=self.backoff_s)
        with tenant_session(self.factory, tenant_id) as s:
            s.add(WebhookDelivery(tenant_id=tenant_id, webhook_id=hook_id, event=event, target=target,
                                  delivered=res.delivered, attempts=res.attempts, last_status=res.last_status,
                                  errors=res.errors or None))
            s.add(AuditLog(tenant_id=tenant_id, actor="system",
                           action="webhook.delivered" if res.delivered else "webhook.failed", target=hook_id,
                           detail={"event": event, "plan_id": target, "attempts": res.attempts,
                                   "last_status": res.last_status}))
            s.commit()

    def drain(self, timeout: float = 30.0) -> None:
        """Wait for queued deliveries (tests, shutdown)."""
        with self._lock:
            futures, self._futures = self._futures, []
        wait(futures, timeout=timeout)
        for f in futures:
            f.result(timeout=0)  # re-raise delivery-bookkeeping errors instead of hiding them
