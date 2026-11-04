"""Signed webhooks with retries (P6d).

Signature header (Stripe-style): `LogiMind-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256>`
over the bytes `f"{t}.".encode() + body`, keyed with the endpoint's secret. Receivers
recompute it with `verify_signature` and reject old timestamps (replay protection).

Delivery goes through a `WebhookSender` adapter: `HttpxSender` for real HTTP and
`FakeSender` (deterministic, offline) for tests and CI. A delivery is retried on network
errors, HTTP 429 and 5xx with exponential back-off; other 4xx answers are final.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

SIGNATURE_HEADER = "LogiMind-Signature"
DEFAULT_BACKOFF_S = (1.0, 2.0, 4.0)  # waits between attempts -> at most 4 attempts
TOLERANCE_S = 300


def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify_signature(secret: str, body: bytes, header: str | None, now: float | None = None,
                     tolerance_s: int = TOLERANCE_S) -> bool:
    if not header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        given = parts["v1"]
    except (ValueError, KeyError):
        return False
    now = time.time() if now is None else now
    if abs(now - ts) > tolerance_s:
        return False
    expected = sign(secret, body, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, given)


class WebhookSender(Protocol):
    def send(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        """POST and return the HTTP status code; raise OSError-like errors on network failure."""


class HttpxSender:
    def __init__(self, timeout_s: float = 5.0):
        self.timeout_s = timeout_s

    def send(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        import httpx
        try:
            return httpx.post(url, content=body, headers=headers, timeout=self.timeout_s).status_code
        except httpx.HTTPError as exc:
            raise ConnectionError(str(exc)) from exc


@dataclass
class FakeSender:
    """Answers from a scripted list of status codes (or exceptions); records every call."""
    script: list[int | Exception] = field(default_factory=list)
    default: int = 200
    calls: list[dict[str, Any]] = field(default_factory=list)

    def send(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.calls.append({"url": url, "body": body, "headers": dict(headers)})
        answer = self.script.pop(0) if self.script else self.default
        if isinstance(answer, Exception):
            raise answer
        return answer


@dataclass
class DeliveryResult:
    delivered: bool
    attempts: int
    last_status: int | None
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def deliver(sender: WebhookSender, url: str, secret: str, event: str, payload: dict[str, Any],
            backoff_s: tuple[float, ...] = DEFAULT_BACKOFF_S, sleep: Callable[[float], None] = time.sleep,
            clock: Callable[[], float] = time.time) -> DeliveryResult:
    body = json.dumps({"event": event, "data": payload}, sort_keys=True, separators=(",", ":")).encode()
    errors: list[str] = []
    status: int | None = None
    for attempt in range(1, len(backoff_s) + 2):
        headers = {"Content-Type": "application/json", "LogiMind-Event": event,
                   SIGNATURE_HEADER: sign(secret, body, int(clock()))}  # fresh timestamp per attempt
        try:
            status = sender.send(url, body, headers)
            if 200 <= status < 300:
                return DeliveryResult(True, attempt, status, errors)
            errors.append(f"attempt {attempt}: HTTP {status}")
            if not _retryable(status):
                break
        except (OSError, ConnectionError, TimeoutError) as exc:
            status = None
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
        if attempt <= len(backoff_s):
            sleep(backoff_s[attempt - 1])
    return DeliveryResult(False, len(errors), status, errors)
