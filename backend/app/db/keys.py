"""Tenants and API keys. Keys look like `lm_<prefix>_<secret>`; only SHA-256(key) is stored.

SHA-256 (not a slow password hash) is enough here because keys are 32 random bytes
from `secrets`, not human-chosen passwords (docs/decisions/0008)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApiKey, Tenant, utcnow


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    key_id: str


def create_tenant(session: Session, name: str) -> Tenant:
    t = Tenant(id=f"ten-{uuid.uuid4().hex[:12]}", name=name)
    session.add(t)
    session.flush()
    return t


def issue_key(session: Session, tenant_id: str, label: str = "") -> tuple[ApiKey, str]:
    """Returns (row, plaintext key). The plaintext is never stored."""
    prefix = secrets.token_hex(6)
    key = f"lm_{prefix}_{secrets.token_urlsafe(32)}"
    row = ApiKey(id=f"key-{uuid.uuid4().hex[:12]}", tenant_id=tenant_id, prefix=prefix, key_hash=hash_key(key),
                 label=label)
    session.add(row)
    session.flush()
    return row, key


def authenticate(session: Session, key: str | None) -> Principal | None:
    """Admin-session lookup by prefix, then constant-time hash comparison."""
    if not key or not key.startswith("lm_") or key.count("_") < 2:
        return None
    prefix = key.split("_", 2)[1]
    row = session.scalars(select(ApiKey).where(ApiKey.prefix == prefix)).first()
    if row is None or row.revoked_at is not None:
        return None
    if not hmac.compare_digest(row.key_hash, hash_key(key)):
        return None
    return Principal(row.tenant_id, row.id)


def revoke_key(session: Session, key_id: str) -> bool:
    row = session.get(ApiKey, key_id)
    if row is None:
        return False
    row.revoked_at = utcnow()
    session.flush()
    return True
