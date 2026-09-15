import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from mcp_server.context import ToolCallerContext
from mcp_server.tools.inventory_tools import InventoryWarningInput
from mcp_server.tools.order_tools import OrderSearchDetailsInput, order_search_details
from mcp_server.tools.parts_tools import (
    PartBySupplierInput,
    PartQueryInput,
    part_query,
)
from mcp_server.tools.suppliers_tools import (
    QuotationQueryInput,
    SupplierQueryInput,
    quotation_query,
    supplier_query,
)
from procurepilot.business.entities import (
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierQuotation,
)
from procurepilot.business.enums import Currency, OrderStatus, PartStatus, SupplierStatus, Unit
from procurepilot.business.value_objects import Money, PositiveQuantity

NOW = datetime(2026, 9, 8, tzinfo=UTC)
READER = ToolCallerContext(
    user_id="reader-1", roles=frozenset({"procurement_reader"}), trace_id="trace-1"
)


class FakeSupplierService:
    async def search(self, criteria):
        return [
            Supplier(f"s-{index}", f"S-{index}", "Supplier", SupplierStatus.ACTIVE)
            for index in range(criteria.limit + 2)
        ]


class FakePartService:
    async def search(self, criteria):
        return [Part("p-1", "P-1", "Part", "Spec", Unit.PIECE, PartStatus.ACTIVE)]

    async def find_by_supplier(self, supplier_id, *, at, limit):
        return await self.search(type("Criteria", (), {"limit": limit})())


class FakeQuotationService:
    async def find_valid_quotes(self, criteria, at):
        return [
            SupplierQuotation(
                "q-1",
                "s-1",
                "p-1",
                Money(Decimal("12.50"), Currency.CNY),
                PositiveQuantity(Decimal("10"), Unit.PIECE),
                3,
                NOW - timedelta(days=1),
                NOW + timedelta(days=1),
                "erp",
                NOW,
            )
        ]


@pytest.mark.asyncio
async def test_success_envelope_and_result_limit() -> None:
    result = await supplier_query(
        SupplierQueryInput(limit=2),
        service=FakeSupplierService(),
        caller=READER,
        timeout_seconds=1,
    )

    assert result.ok is True
    assert result.data is not None and len(result.data) == 2
    assert result.trace_id == "trace-1"


@pytest.mark.asyncio
async def test_quotation_contains_required_evidence_fields() -> None:
    result = await quotation_query(
        QuotationQueryInput(part_id="p-1", at=NOW),
        service=FakeQuotationService(),
        caller=READER,
        timeout_seconds=1,
    )

    assert result.data is not None
    quote = result.data[0].model_dump()
    assert {
        "quotation_id",
        "source",
        "collected_at",
        "valid_from",
        "valid_until",
        "minimum_order_quantity",
        "currency",
        "unit",
    } <= quote.keys()


@pytest.mark.asyncio
async def test_timeout_is_returned_as_stable_error() -> None:
    class SlowPartService(FakePartService):
        async def search(self, criteria):
            await asyncio.sleep(0.05)
            return []

    result = await part_query(
        PartQueryInput(), service=SlowPartService(), caller=READER, timeout_seconds=0.001
    )

    assert result.error is not None
    assert result.error.code == "DEPENDENCY_TIMEOUT"
    assert result.error.retryable is True


@pytest.mark.asyncio
async def test_order_query_requires_server_supplied_read_role() -> None:
    class FakeOrderService:
        async def search(self, criteria):
            return []

    denied = await order_search_details(
        OrderSearchDetailsInput(),
        service=FakeOrderService(),
        caller=READER,
        timeout_seconds=1,
    )

    assert denied.error is not None and denied.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_order_query_returns_version_and_line_details() -> None:
    class FakeOrderService:
        async def search(self, criteria):
            return [
                PurchaseOrder(
                    order_id="o-1",
                    order_no="PO-1",
                    supplier_id="s-1",
                    status=OrderStatus.CREATED,
                    currency=Currency.CNY,
                    items=(
                        PurchaseOrderItem(
                            "oi-1",
                            "p-1",
                            PositiveQuantity(Decimal("2"), Unit.PIECE),
                            Money(Decimal("10"), Currency.CNY),
                            "q-1",
                        ),
                    ),
                    idempotency_key="key-1",
                    version=4,
                )
            ]

    caller = ToolCallerContext(
        user_id="order-reader",
        roles=frozenset({"order_reader"}),
        trace_id="trace-order",
    )
    result = await order_search_details(
        OrderSearchDetailsInput(order_id="o-1"),
        service=FakeOrderService(),
        caller=caller,
        timeout_seconds=1,
    )

    assert result.data is not None
    assert result.data[0].version == 4
    assert result.data[0].items[0].quotation_id == "q-1"


@pytest.mark.parametrize(
    "input_model",
    [
        SupplierQueryInput,
        PartQueryInput,
        PartBySupplierInput,
        QuotationQueryInput,
        InventoryWarningInput,
        OrderSearchDetailsInput,
    ],
)
def test_business_inputs_cannot_override_identity(input_model) -> None:
    with pytest.raises(ValueError):
        input_model.model_validate({"user_id": "attacker", "roles": ["admin"]})
