import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from procurepilot.config import Settings
from procurepilot.infrastructure.database import create_database_engine

REQUIRED_TABLES = {
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


async def _table_names(settings: Settings) -> set[str]:
    engine = create_database_engine(settings, require_test_database=True)
    try:
        async with engine.connect() as connection:
            names = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
            return set(names)
    finally:
        await engine.dispose()


def test_migration_can_upgrade_downgrade_and_replay(
    alembic_config: Config,
    mysql_test_settings: Settings,
) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert REQUIRED_TABLES <= asyncio.run(_table_names(mysql_test_settings))

    command.downgrade(alembic_config, "base")
    assert REQUIRED_TABLES.isdisjoint(asyncio.run(_table_names(mysql_test_settings)))

    command.upgrade(alembic_config, "head")
    assert REQUIRED_TABLES <= asyncio.run(_table_names(mysql_test_settings))
