"""Database models. Every tenant-owned table carries `tenant_id` (TenantOwned mixin);
tenant sessions (app/db/session.py) filter and check it automatically."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TenantOwned:
    """Marker mixin: rows belong to exactly one tenant."""
    tenant_id: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.id"), index=True, nullable=False)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(TenantOwned, Base):
    """Only a SHA-256 hash of the key is stored; the plaintext is shown once at creation."""
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Plan(TenantOwned, Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    instance: Mapped[dict] = mapped_column(JSON, nullable=False)
    requested_engine: Mapped[str] = mapped_column(String(20), nullable=False)
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    time_limit_s: Mapped[float] = mapped_column(nullable=False)
    selection: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # P7 replanning: the plan this one replaces, the disruption event, and the replan record
    parent_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("plans.id"), nullable=True, index=True)
    event: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    replan: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AuditLog(TenantOwned, Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)  # api key id or "system"
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Webhook(TenantOwned, Base):
    """Endpoint that receives signed events. The secret signs payloads, so it is stored (shown once)."""
    __tablename__ = "webhooks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    secret: Mapped[str] = mapped_column(String(100), nullable=False)
    events: Mapped[list] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookDelivery(TenantOwned, Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    webhook_id: Mapped[str] = mapped_column(String(40), ForeignKey("webhooks.id"), index=True, nullable=False)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[str] = mapped_column(String(120), default="")
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


TENANT_MODELS = (ApiKey, Plan, AuditLog, Webhook, WebhookDelivery)
