from sqlalchemy import Numeric, UniqueConstraint

from procurepilot.infrastructure.orm_models import Base

EXPECTED_TABLES = {
    "suppliers",
    "parts",
    "supplier_quotations",
    "inventory_items",
    "purchase_orders",
    "purchase_order_items",
    "order_operations",
    "approval_grants",
    "idempotency_records",
    "operation_audits",
}


def test_metadata_contains_required_procurement_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_business_keys_have_database_unique_constraints() -> None:
    expected = {
        "suppliers": {"supplier_code"},
        "parts": {"part_code"},
        "purchase_orders": {"order_no", "idempotency_key"},
    }
    for table_name, columns in expected.items():
        table = Base.metadata.tables[table_name]
        unique_columns = {
            column.name for column in table.columns if column.unique
        } | {
            next(iter(constraint.columns)).name
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1
        }
        assert columns <= unique_columns


def test_money_and_quantity_columns_use_fixed_decimal_precision() -> None:
    quotations = Base.metadata.tables["supplier_quotations"]
    items = Base.metadata.tables["purchase_order_items"]

    for column, expected_scale in (
        (quotations.c.unit_price, 4),
        (quotations.c.minimum_order_quantity, 6),
        (items.c.unit_price, 4),
        (items.c.quantity, 6),
    ):
        assert isinstance(column.type, Numeric)
        assert column.type.precision == 19
        assert column.type.scale == expected_scale


def test_versioned_tables_default_to_one() -> None:
    for table_name in ("suppliers", "inventory_items", "purchase_orders", "order_operations"):
        default = Base.metadata.tables[table_name].c.version.default
        assert default is not None
        assert default.arg == 1
