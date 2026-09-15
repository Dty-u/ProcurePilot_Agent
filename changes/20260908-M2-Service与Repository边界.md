# M2 Service 与 Repository 边界 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用 Protocol、InMemory Repository 和 Unit of Work 建立可测试的采购应用服务边界。

**Architecture:** Service 负责编排领域对象和 Repository；Repository 只负责保存与查询；Unit of Work 控制原子提交。业务层不得读取环境变量，也不得依赖 Agent、MCP 或 FastAPI。

**Tech Stack:** Python Protocol、asyncio、pytest-asyncio、领域模型

---

## 前置条件

- M1 领域测试全部通过。
- 本阶段不接 MySQL；先通过 InMemory 实现证明接口和事务语义。

### Task 1: Repository Protocol 与查询对象

**Files:**
- Create: `src/procurepilot/business/repositories.py`
- Create: `src/procurepilot/business/query_models.py`
- Test: `src/tests/unit/business/test_repository_contracts.py`

定义异步 Protocol：`SupplierRepository`、`PartRepository`、`QuotationRepository`、`InventoryRepository`、`OrderRepository`、`ApprovalRepository`、`AuditRepository` 和 `UnitOfWork`。查询条件使用显式对象，不接受任意 SQL、字典或字段名。

关键签名：

```python
class UnitOfWork(Protocol):
    suppliers: SupplierRepository
    parts: PartRepository
    quotations: QuotationRepository
    inventory: InventoryRepository
    orders: OrderRepository
    approvals: ApprovalRepository
    audits: AuditRepository

    async def __aenter__(self) -> "UnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

测试 Protocol 所需方法和查询对象的严格字段校验。

### Task 2: InMemory Repository 与事务

**Files:**
- Create: `src/procurepilot/business/in_memory.py`
- Test: `src/tests/unit/business/test_in_memory_uow.py`

先写失败测试，证明：未调用 `commit()` 的改动在退出上下文后回滚；异常时回滚；提交后数据可见；返回对象不会通过共享引用绕过 Repository 更新；重复业务 ID 和幂等键产生冲突。

实现时每个 UoW 使用工作副本，commit 时原子替换共享状态。并发版本冲突通过实体 `version` 检测，不使用线程锁掩盖逻辑错误。

### Task 3: 查询与比价 Service

**Files:**
- Create: `src/procurepilot/business/services/catalog.py`
- Create: `src/procurepilot/business/services/comparison.py`
- Test: `src/tests/unit/business/services/test_comparison_service.py`

固定接口：

```text
SupplierService.search(criteria)
PartService.search(criteria)
QuotationService.find_valid_quotes(criteria, at)
ComparisonService.compare_suppliers(request, at)
InventoryService.get_warnings(criteria)
```

`ComparisonService` 只使用有效报价，规范化同币种和同单位数据，输出候选、被排除项及原因；本阶段不做汇率换算，币种不一致必须明确排除或报信息不足。

测试无报价、过期报价、MOQ、币种不一致、同价不同交期和禁用供应商。

### Task 4: 订单准备与执行 Service

**Files:**
- Create: `src/procurepilot/business/services/order.py`
- Test: `src/tests/unit/business/services/test_order_service.py`

固定接口：

```python
async def prepare(request: PrepareOrderRequest, context: ActorContext) -> PreparedOrder
async def execute(request: ExecuteOrderRequest, context: ActorContext) -> PurchaseOrder
```

M2 先实现订单预校验、规范化参数和幂等接口；审批实体在 M6 完整实现。`execute` 必须通过一个可替换的审批校验接口，默认拒绝，没有审批时不得写入。

测试同一幂等键只产生一个结果、权限不足、报价变化、版本冲突，以及订单写入后审计失败时整笔回滚。

### Task 5: 错误层级、文档与门禁

**Files:**
- Modify: `src/procurepilot/business/errors.py`
- Modify: `rules/工程架构.md`
- Modify: `wiki/业务模型.md`

错误层级固定为：`DomainValidationError`、`EntityNotFoundError`、`ConflictError`、`PermissionDeniedError`、`ApprovalRequiredError`、`InfrastructureError`。禁止在业务层返回 HTTP 状态码或 MCP 错误信封。

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest src/tests/unit/business -v
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src
git diff --check
```

**完成标准：** 所有 Service 可在 InMemory UoW 上运行，事务、幂等和错误语义均有测试证据。

**建议提交：** `feat: add procurement services and repository contracts`

