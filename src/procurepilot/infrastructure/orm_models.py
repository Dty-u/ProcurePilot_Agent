"""置于采购领域层之外的 SQLAlchemy 持久化模型。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SupplierORM(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    supplier_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    delivery_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"), nullable=False)


class PartORM(Base):
    __tablename__ = "parts"

    part_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    part_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specification: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class SupplierQuotationORM(Base):
    __tablename__ = "supplier_quotations"
    __table_args__ = (
        Index("ix_supplier_quotations_part_supplier", "part_id", "supplier_id"),
        Index("ix_supplier_quotations_validity", "valid_from", "valid_until"),
    )

    quotation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    supplier_id: Mapped[str] = mapped_column(
        ForeignKey("suppliers.supplier_id"), nullable=False
    )
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.part_id"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    minimum_order_quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class InventoryItemORM(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("part_id", "warehouse_code", name="uq_inventory_part_warehouse"),
    )

    inventory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.part_id"), nullable=False)
    warehouse_code: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    on_hand_quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    safety_stock: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"), nullable=False)


class PurchaseOrderORM(Base):
    __tablename__ = "purchase_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    supplier_id: Mapped[str] = mapped_column(
        ForeignKey("suppliers.supplier_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"), nullable=False)
    items: Mapped[list["PurchaseOrderItemORM"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    idempotency_record: Mapped["IdempotencyRecordORM"] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )


class PurchaseOrderItemORM(Base):
    __tablename__ = "purchase_order_items"

    order_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_orders.order_id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.part_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quotation_id: Mapped[str | None] = mapped_column(
        ForeignKey("supplier_quotations.quotation_id")
    )


class OrderOperationORM(Base):
    __tablename__ = "order_operations"

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_orders.order_id"))
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_grants: Mapped[list["ApprovalGrantORM"]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
    )


class ApprovalGrantORM(Base):
    __tablename__ = "approval_grants"
    __table_args__ = (
        UniqueConstraint("operation_id", "actor_id", name="uq_approval_operation_actor"),
    )

    grant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("order_operations.operation_id"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    operation: Mapped[OrderOperationORM] = relationship(back_populates="approval_grants")


class IdempotencyRecordORM(Base):
    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_orders.order_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class OperationAuditORM(Base):
    __tablename__ = "operation_audits"
    __table_args__ = (Index("ix_operation_audits_object", "object_type", "object_id"),)

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_summary: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64))
