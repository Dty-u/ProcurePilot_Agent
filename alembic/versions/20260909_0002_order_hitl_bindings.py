"""Add parameter-bound HITL operation and approval fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0002"
down_revision: str | None = "20260908_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_operations",
        sa.Column("thread_id", sa.String(128), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "order_operations",
        sa.Column("normalized_payload", sa.JSON(), nullable=False, server_default=sa.text("('{}')")),
    )
    op.add_column(
        "order_operations",
        sa.Column("expires_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.add_column(
        "approval_grants",
        sa.Column("thread_id", sa.String(128), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "approval_grants",
        sa.Column("action", sa.String(32), nullable=False, server_default="create"),
    )
    op.add_column(
        "approval_grants",
        sa.Column("decision", sa.String(16), nullable=False, server_default="approve"),
    )
    op.add_column(
        "approval_grants",
        sa.Column("expires_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_column("approval_grants", "expires_at")
    op.drop_column("approval_grants", "decision")
    op.drop_column("approval_grants", "action")
    op.drop_column("approval_grants", "thread_id")
    op.drop_column("order_operations", "expires_at")
    op.drop_column("order_operations", "normalized_payload")
    op.drop_column("order_operations", "thread_id")
