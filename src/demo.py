import asyncio

from procurepilot.business.entities import Supplier
from procurepilot.business.enums import SupplierStatus
from procurepilot.config import Settings
from procurepilot.infrastructure.database import (
    create_database_engine,
    create_session_factory,
)
from procurepilot.infrastructure.mysql_uow import MySQLUnitOfWork


async def main() -> None:
    settings = Settings()

    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        supplier = Supplier(
            supplier_id="supplier-002",
            supplier_code="SUP-002",
            name="测试供应商2",
            status=SupplierStatus.ACTIVE,
        )

        async with MySQLUnitOfWork(session_factory) as uow:
            await uow.suppliers.add(supplier)
            await uow.commit()

        print("供应商写入成功")

        # 再从数据库读取，验证写入结果
        async with MySQLUnitOfWork(session_factory) as uow:
            saved_supplier = await uow.suppliers.get_by_id("supplier-001")

        print(saved_supplier)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())