"""webhooks and webhook deliveries (P6d)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _tenant_fk() -> sa.Column:
    return sa.Column("tenant_id", sa.String(40), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(40), primary_key=True),
        _tenant_fk(),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("secret", sa.String(100), nullable=False),
        sa.Column("events", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        _tenant_fk(),
        sa.Column("webhook_id", sa.String(40), sa.ForeignKey("webhooks.id"), nullable=False, index=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("target", sa.String(120)),
        sa.Column("delivered", sa.Boolean),
        sa.Column("attempts", sa.Integer),
        sa.Column("last_status", sa.Integer, nullable=True),
        sa.Column("errors", sa.JSON, nullable=True),
        sa.Column("at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
