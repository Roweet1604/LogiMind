"""Database models. Every tenant-owned table carries `tenant_id` (TenantOwned mixin);
tenant sessions (app/db/session.py) filter and check it automatically."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class DriverLink(TenantOwned, Base):
    """A short-lived signed link that gives one driver access to one route of one plan (P9).
    The token itself is not stored; this row lets a dispatcher list and revoke links."""
    __tablename__ = "driver_links"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(40), ForeignKey("plans.id"), index=True, nullable=False)
    route_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StopEvent(TenantOwned, Base):
    """A driver's report for one stop: delivered, or failed with a reason. The latest event is the stop's status."""
    __tablename__ = "stop_events"
    __table_args__ = (UniqueConstraint("tenant_id", "client_event_id", name="uq_stop_events_client_event"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(String(40), ForeignKey("plans.id"), index=True, nullable=False)
    route_index: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    link_id: Mapped[str] = mapped_column(String(40), ForeignKey("driver_links.id"), nullable=False)
    client_event_id: Mapped[str] = mapped_column(String(64), nullable=False)  # makes offline resends safe
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # driver's clock
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PodPhoto(TenantOwned, Base):
    """Proof-of-delivery photo. The file lives under <data dir>/pod/<tenant>/<id><ext>; the name is ours."""
    __tablename__ = "pod_photos"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(40), ForeignKey("plans.id"), index=True, nullable=False)
    route_index: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    link_id: Mapped[str] = mapped_column(String(40), ForeignKey("driver_links.id"), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerContact(TenantOwned, Base):
    """How to reach a customer (by the customer id used in the tenant's orders) and whether they opted in.
    Messages are sent only while opt_in is true; the default is false (explicit opt-in)."""
    __tablename__ = "customer_contacts"
    __table_args__ = (UniqueConstraint("tenant_id", "customer_id", name="uq_customer_contacts_customer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    channel: Mapped[str] = mapped_column(String(10), nullable=False)  # "sms" or "email"
    address: Mapped[str] = mapped_column(String(320), nullable=False)
    opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    opt_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationLog(TenantOwned, Base):
    """Every customer message LogiMind sent or decided not to send, with the reason. The recipient is masked."""
    __tablename__ = "notification_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("plans.id"), index=True, nullable=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(10), nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(80), nullable=True)  # masked
    message: Mapped[str | None] = mapped_column(Text, nullable=True)  # None when not sent
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


TENANT_MODELS = (ApiKey, Plan, AuditLog, Webhook, WebhookDelivery, DriverLink, StopEvent, PodPhoto,
                 CustomerContact, NotificationLog)


class Job(Base):
    """A durable solver job (P6 queue, decision 0021). Not TenantOwned: benchmark jobs have no tenant, and only
    the worker reads this table (admin session). The worker writes a job's results through a tenant session for
    `tenant_id`, so a job can never change another tenant's plan. Tenants see their own jobs only through
    their plans (an explicit tenant filter)."""
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)        # plan | replan | benchmark
    lane: Mapped[str] = mapped_column(String(20), nullable=False)        # planning | benchmark
    tenant_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("tenants.id"), index=True, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("plans.id"), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # queued|running|completed|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)     # benchmark jobs only
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list | None] = mapped_column(JSON, nullable=True)    # requeues after a worker stopped
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueueLock(Base):
    """One row. Every claim first updates it, which serializes claims on SQLite and PostgreSQL alike."""
    __tablename__ = "queue_lock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claims: Mapped[int] = mapped_column(Integer, default=0)
