"""Create the initial procurement persistence schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("supplier_id", sa.String(64), primary_key=True),
        sa.Column("supplier_code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 2)),
        sa.Column("delivery_score", sa.Numeric(5, 2)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_suppliers_status", "suppliers", ["status"])

    op.create_table(
        "parts",
        sa.Column("part_id", sa.String(64), primary_key=True),
        sa.Column("part_code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("specification", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_index("ix_parts_status", "parts", ["status"])
    op.create_index("ix_parts_unit", "parts", ["unit"])

    op.create_table(
        "supplier_quotations",
        sa.Column("quotation_id", sa.String(64), primary_key=True),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.supplier_id"), nullable=False),
        sa.Column("part_id", sa.String(64), sa.ForeignKey("parts.part_id"), nullable=False),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("minimum_order_quantity", sa.Numeric(19, 6), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_supplier_quotations_part_supplier",
        "supplier_quotations",
        ["part_id", "supplier_id"],
    )
    op.create_index(
        "ix_supplier_quotations_validity",
        "supplier_quotations",
        ["valid_from", "valid_until"],
    )

    op.create_table(
        "inventory_items",
        sa.Column("inventory_id", sa.String(64), primary_key=True),
        sa.Column("part_id", sa.String(64), sa.ForeignKey("parts.part_id"), nullable=False),
        sa.Column("warehouse_code", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("on_hand_quantity", sa.Numeric(19, 6), nullable=False),
        sa.Column("reserved_quantity", sa.Numeric(19, 6), nullable=False),
        sa.Column("safety_stock", sa.Numeric(19, 6), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("part_id", "warehouse_code", name="uq_inventory_part_warehouse"),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("order_id", sa.String(64), primary_key=True),
        sa.Column("order_no", sa.String(64), nullable=False, unique=True),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.supplier_id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])

    op.create_table(
        "purchase_order_items",
        sa.Column("order_item_id", sa.String(64), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(64),
            sa.ForeignKey("purchase_orders.order_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_id", sa.String(64), sa.ForeignKey("parts.part_id"), nullable=False),
        sa.Column("quantity", sa.Numeric(19, 6), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("quotation_id", sa.String(64), sa.ForeignKey("supplier_quotations.quotation_id")),
    )
    op.create_index("ix_purchase_order_items_order_id", "purchase_order_items", ["order_id"])

    op.create_table(
        "order_operations",
        sa.Column("operation_id", sa.String(64), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), sa.ForeignKey("purchase_orders.order_id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
    )
    op.create_index("ix_order_operations_status", "order_operations", ["status"])

    op.create_table(
        "approval_grants",
        sa.Column("grant_id", sa.String(64), primary_key=True),
        sa.Column(
            "operation_id",
            sa.String(64),
            sa.ForeignKey("order_operations.operation_id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
        sa.UniqueConstraint("operation_id", "actor_id", name="uq_approval_operation_actor"),
    )
    op.create_index("ix_approval_grants_operation_id", "approval_grants", ["operation_id"])

    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(64),
            sa.ForeignKey("purchase_orders.order_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "operation_audits",
        sa.Column("audit_id", sa.String(64), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("parameter_summary", sa.Text(), nullable=False),
        sa.Column("result", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.String(64)),
    )
    op.create_index("ix_operation_audits_trace_id", "operation_audits", ["trace_id"])
    op.create_index(
        "ix_operation_audits_object",
        "operation_audits",
        ["object_type", "object_id"],
    )


def downgrade() -> None:
    op.drop_table("operation_audits")
    op.drop_table("idempotency_records")
    op.drop_table("approval_grants")
    op.drop_table("order_operations")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("inventory_items")
    op.drop_table("supplier_quotations")
    op.drop_table("parts")
    op.drop_table("suppliers")
