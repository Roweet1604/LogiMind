"""Signed driver-link tokens: `dl1.<base64url claims>.<base64url HMAC-SHA256>`.

Claims: l = link id, t = tenant id, p = plan id, r = route index, e = expiry (unix seconds).
A token is accepted only if the signature matches, it has not expired, and its link row (looked up
by id) still exists, is not revoked and names the same tenant, plan and route. So a link for one
route can never be turned into a link for another route, plan or tenant without the server secret.

The secret comes from LOGIMIND_DRIVER_LINK_SECRET (at least 32 characters). Without it a random
secret is made per process, so links stop working when the server restarts (fine for development;
set the variable in any shared deployment). Secrets are never written to disk or the database.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass

log = logging.getLogger(__name__)
PREFIX = "dl1"
MIN_SECRET_LEN = 32


class LinkError(PermissionError):
    """The token is missing, malformed, tampered with, expired or revoked (always answered with 401)."""


@dataclass(frozen=True)
class LinkClaims:
    link_id: str
    tenant_id: str
    plan_id: str
    route_index: int
    expires: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def secret_from_env() -> bytes:
    value = os.environ.get("LOGIMIND_DRIVER_LINK_SECRET", "")
    if value:
        if len(value) < MIN_SECRET_LEN:
            raise ValueError(f"LOGIMIND_DRIVER_LINK_SECRET must be at least {MIN_SECRET_LEN} characters")
        return value.encode()
    log.warning("LOGIMIND_DRIVER_LINK_SECRET is not set: using a random per-process secret; "
                "driver links stop working when the server restarts")
    return secrets.token_bytes(32)


class LinkSigner:
    def __init__(self, secret: bytes):
        if len(secret) < MIN_SECRET_LEN:
            raise ValueError("driver-link secret too short")
        self._secret = secret

    def _mac(self, body: str) -> str:
        return _b64(hmac.new(self._secret, f"{PREFIX}.{body}".encode(), hashlib.sha256).digest())

    def sign(self, c: LinkClaims) -> str:
        body = _b64(json.dumps({"l": c.link_id, "t": c.tenant_id, "p": c.plan_id, "r": c.route_index,
                                "e": c.expires}, separators=(",", ":"), sort_keys=True).encode())
        return f"{PREFIX}.{body}.{self._mac(body)}"

    def verify(self, token: str | None, now: float) -> LinkClaims:
        if not token or len(token) > 1000:
            raise LinkError("missing driver link")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != PREFIX:
            raise LinkError("malformed driver link")
        _, body, mac = parts
        if not hmac.compare_digest(mac, self._mac(body)):
            raise LinkError("driver link signature does not match")
        try:
            raw = json.loads(_unb64(body))
            claims = LinkClaims(str(raw["l"]), str(raw["t"]), str(raw["p"]), int(raw["r"]), int(raw["e"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise LinkError("malformed driver link") from exc
        if now >= claims.expires:
            raise LinkError("driver link has expired; ask the dispatcher for a new one")
        return claims
