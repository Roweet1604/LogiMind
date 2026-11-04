"""Message sender adapter. The only implementation is `StubSender`: it logs the message and keeps it in
memory. It never contacts a network or a paid SMS/e-mail provider (PLAN.md: a real provider is deferred).
Every send is also stored in the notification log table by NotificationService."""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger("logimind.messaging")


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider: str
    provider_id: str | None = None
    error: str | None = None


class MessageSender(Protocol):
    name: str

    def send(self, channel: str, to: str, text: str) -> SendResult: ...


def mask(address: str) -> str:
    """'+919812345678' -> '+91******78'; 'asha@example.com' -> 'a***@example.com'."""
    if "@" in address:
        user, _, domain = address.partition("@")
        return f"{user[:1]}***@{domain}"
    return address[:3] + "*" * max(0, len(address) - 5) + address[-2:]


@dataclass
class StubSender:
    """Logs instead of sending. `fail_with` makes every send fail (tests of the failure path)."""
    name: str = "stub"
    fail_with: str | None = None
    sent: list[dict] = field(default_factory=list)

    def send(self, channel: str, to: str, text: str) -> SendResult:
        if self.fail_with:
            log.warning("stub %s to %s failed: %s", channel, mask(to), self.fail_with)
            return SendResult(False, self.name, error=self.fail_with)
        msg_id = f"stub-{uuid.uuid4().hex[:12]}"
        self.sent.append({"id": msg_id, "channel": channel, "to": to, "text": text})
        log.info("stub %s to %s (not sent; no provider): %s", channel, mask(to), text)
        return SendResult(True, self.name, msg_id)


def sender_from_env() -> MessageSender:
    name = os.environ.get("LOGIMIND_NOTIFY_PROVIDER", "stub")
    if name != "stub":
        raise ValueError(f"LOGIMIND_NOTIFY_PROVIDER={name!r}: only 'stub' exists (no paid provider is built in)")
    return StubSender()
