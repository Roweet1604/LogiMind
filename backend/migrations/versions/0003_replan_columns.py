"""plans: parent_id, event, replan (P7)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("parent_id", sa.String(40), sa.ForeignKey("plans.id", name="fk_plans_parent"),
                                   nullable=True))
        batch.add_column(sa.Column("event", sa.JSON, nullable=True))
        batch.add_column(sa.Column("replan", sa.JSON, nullable=True))
        batch.create_index("ix_plans_parent_id", ["parent_id"])


def downgrade() -> None:
    with op.batch_alter_table("plans") as batch:
        batch.drop_index("ix_plans_parent_id")
        batch.drop_column("replan")
        batch.drop_column("event")
        batch.drop_column("parent_id")
