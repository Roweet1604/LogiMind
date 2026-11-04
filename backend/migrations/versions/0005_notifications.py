"""customer contacts (opt-in) and the notification log (P9)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _tenant_fk() -> sa.Column:
    return sa.Column("tenant_id", sa.String(40), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        _tenant_fk(),
        sa.Column("customer_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("opt_in", sa.Boolean),
        sa.Column("opt_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opt_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "customer_id", name="uq_customer_contacts_customer"),
    )
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        _tenant_fk(),
        sa.Column("plan_id", sa.String(40), sa.ForeignKey("plans.id"), nullable=True, index=True),
        sa.Column("customer_id", sa.Integer, nullable=False),
        sa.Column("template", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(10), nullable=True),
        sa.Column("recipient", sa.String(80), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("customer_contacts")
