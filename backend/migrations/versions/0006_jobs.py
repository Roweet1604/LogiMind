"""durable job queue: jobs + queue_lock (P6, decision 0021)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("lane", sa.String(20), nullable=False),
        sa.Column("tenant_id", sa.String(40), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("plan_id", sa.String(40), sa.ForeignKey("plans.id"), nullable=True, index=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("state", sa.String(20), nullable=False, index=True),
        sa.Column("attempts", sa.Integer),
        sa.Column("max_attempts", sa.Integer),
        sa.Column("worker_id", sa.String(80), nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("history", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "queue_lock",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("claims", sa.Integer),
    )
    op.execute("INSERT INTO queue_lock (id, claims) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("queue_lock")
    op.drop_table("jobs")
