"""driver links, stop events, proof-of-delivery photos (P9)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _tenant_fk() -> sa.Column:
    return sa.Column("tenant_id", sa.String(40), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def _plan_fk() -> sa.Column:
    return sa.Column("plan_id", sa.String(40), sa.ForeignKey("plans.id"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "driver_links",
        sa.Column("id", sa.String(40), primary_key=True),
        _tenant_fk(),
        _plan_fk(),
        sa.Column("route_index", sa.Integer, nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "stop_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        _tenant_fk(),
        _plan_fk(),
        sa.Column("route_index", sa.Integer, nullable=False),
        sa.Column("customer_id", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(40), nullable=True),
        sa.Column("note", sa.String(500)),
        sa.Column("link_id", sa.String(40), sa.ForeignKey("driver_links.id"), nullable=False),
        sa.Column("client_event_id", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "client_event_id", name="uq_stop_events_client_event"),
    )
    op.create_table(
        "pod_photos",
        sa.Column("id", sa.String(40), primary_key=True),
        _tenant_fk(),
        _plan_fk(),
        sa.Column("route_index", sa.Integer, nullable=False),
        sa.Column("customer_id", sa.Integer, nullable=False),
        sa.Column("link_id", sa.String(40), sa.ForeignKey("driver_links.id"), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("pod_photos")
    op.drop_table("stop_events")
    op.drop_table("driver_links")
