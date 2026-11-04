"""tenants, api keys, plans, audit log (P6a)

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _tenant_fk() -> sa.Column:
    return sa.Column("tenant_id", sa.String(40), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(40), primary_key=True),
        _tenant_fk(),
        sa.Column("prefix", sa.String(16), nullable=False, unique=True, index=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.String(40), primary_key=True),
        _tenant_fk(),
        sa.Column("instance", sa.JSON, nullable=False),
        sa.Column("requested_engine", sa.String(20), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("time_limit_s", sa.Float, nullable=False),
        sa.Column("selection", sa.JSON, nullable=True),
        sa.Column("state", sa.String(20)),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        _tenant_fk(),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target", sa.String(120)),
        sa.Column("detail", sa.JSON, nullable=True),
        sa.Column("at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for table in ("audit_log", "plans", "api_keys", "tenants"):
        op.drop_table(table)
