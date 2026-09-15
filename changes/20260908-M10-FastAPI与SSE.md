# M10 FastAPI 与 SSE Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 通过 FastAPI 提供流式对话、中断恢复和展示历史接口，完成后端端到端验收。

**Architecture:** FastAPI 只负责鉴权上下文、HTTP 校验、Agent 生命周期和 SSE 转换。业务规则仍在 Service，工具规则仍在 MCP，Agent 内部 graph state 不直接暴露。一次 SSE 连接同时消费 messages 与 values，并优先处理 interrupt。

**Tech Stack:** FastAPI、Uvicorn、SSE、DeepAgents/LangGraph、httpx、pytest

---

## 前置条件

- M0–M9 的非 live 门禁通过；M9 live 状态必须在交付说明中明确。
- 本阶段只实现后端，不创建 Vue、React 或静态管理页面。

### Task 1: API Schema 与测试认证

**Files:**
- Create: `src/api_view/schemas.py`
- Create: `src/api_view/auth.py`
- Test: `src/tests/unit/api_view/test_auth_and_schemas.py`

`ChatRequest` 只包含 message 和可选 thread_id，不接收 user_id/roles。`ResumeRequest` 包含 interrupt_id 和 supplement/decisions 二选一。测试认证适配器从受控 Header 映射固定测试用户，只允许 `APP_ENV=test|development`；生产环境未配置真实认证时启动失败。

### Task 2: 应用生命周期

**Files:**
- Create: `src/api_view/app.py`
- Create: `src/api_view/container.py`
- Test: `src/tests/integration/api_view/test_lifespan.py`

lifespan 按顺序初始化 Settings、业务 MySQL engine/UoW、MCP Client、Agent MySQL checkpointer/store、MySQL Resume Service、MySQL 展示消息 Repository、Sandbox Client 和 Agent。失败时逆序关闭已创建资源。模块导入不连接外部系统，不在事件循环内调用 `asyncio.run()`。

### Task 3: SSE 信封和转换器

**Files:**
- Create: `src/api_view/sse.py`
- Test: `src/tests/unit/api_view/test_sse_mapper.py`

定义 `SSEEnvelope(version, event_id, event, thread_id, timestamp, source, payload)`。允许事件固定为 token、tool_start、tool_args、tool_result、tool_end、interrupt、done。

转换器同时处理 `stream_mode=["messages", "values"]`。每个 chunk 先检查 values interrupt；发现中断时发送 interrupt，再发送 `done(interrupted=true)` 并结束本轮。工具参数和结果先脱敏、限长；大型结果只返回 artifact reference。

### Task 4: Chat 与 Resume 路由

**Files:**
- Create: `src/api_view/routes/__init__.py`
- Create: `src/api_view/routes/chat.py`
- Test: `src/tests/integration/api_view/test_chat_stream.py`

实现：

```text
POST /api/chat/stream
POST /api/chat/{thread_id}/resume
```

Chat 创建或复用当前用户拥有的 thread；Resume 调用 M8 ResumeService 验证用户、thread、interrupt 和一次性状态。连接断开时取消当前读取任务，但绝不自动重放订单写工具。

测试普通 token 流、工具流、中断优先、补充恢复、批准、拒绝、重复 resume、跨用户、客户端断线和依赖异常。

### Task 5: 历史会话接口

**Files:**
- Create: `src/api_view/routes/history.py`
- Test: `src/tests/integration/api_view/test_history_routes.py`

实现当前用户的会话列表、指定 thread 展示消息查询和展示历史删除。分页有固定上限。删除只作用于展示消息；checkpoint、用户 Memory、订单和审计保持不变。跨用户查询返回 404 或统一拒绝语义，避免枚举 thread。

### Task 6: 日志、错误和可观测性

**Files:**
- Create: `src/procurepilot/observability.py`
- Test: `src/tests/security/test_api_redaction.py`

结构化日志至少包含 trace_id、thread_id、脱敏用户标识、Agent 和工具名。禁止记录 Prompt 全文、API Key、MySQL DSN、审批凭证、原始工具大结果和服务器绝对报告路径。流开始后发生错误时通过安全 SSE error/done 语义结束，不发送 HTML 堆栈。

### Task 7: 端到端验收

**Files:**
- Test: `src/tests/e2e/test_analysis_flow.py`
- Test: `src/tests/e2e/test_order_approval_flow.py`

固定验收：

1. 比价请求返回带 quotation ID、来源和时间的分析。
2. 缺字段订单先中断，补充后进入审批。
3. reject 后零写入。
4. approve 后只创建一次并有审计。
5. 审批后参数变化强制重新审批。
6. 同一 thread 可恢复，跨用户被拒绝。
7. 模型、MCP、MySQL 或 Sandbox 超时时不伪造成功。
8. 七类 SSE 事件顺序和脱敏符合契约。

完整门禁：

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src
git diff --check
```

启动命令写入 README，并使用实际配置端口：

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m uvicorn api_view.app:create_app --factory --host 127.0.0.1 --port 18000
```

同步全部相关 Wiki，清楚区分已自动验证、live 验证和未实现能力。

**完成标准：** FastAPI/SSE、HITL 恢复、历史隔离和两个端到端场景全部有测试或明确 live 证据。

**建议提交：** `feat: expose procurepilot agent over fastapi sse`

## 实施状态（2026-09-15）

- Task 1–6 已实现：不接收身份字段的 HTTP Schema、受控环境 Header 认证、显式 lifespan、七类 SSE 事件、Chat/Resume/历史路由、展示消息脱敏和结构化观测字段。
- Agent 中断在发送 SSE 前登记到 Resume Service；HTTP 恢复只提交 `interrupt_id` 和 supplement/decision，action 与参数摘要从服务端记录获取，消费成功后才构造 LangGraph `Command`。
- Task 7 已有使用 Fake 外部依赖的后端端到端测试，覆盖报价溯源、reject 零写入、approve 单次写入、重放拒绝、身份伪造拒绝和历史隔离。
- `APP_ENV=production` 在未配置真实认证提供者时会启动失败。当前实现的 Header 认证只允许 `test|development`，不是生产认证。
- M10 非 live 完成标准已达到；真实模型、MySQL 和 OpenSandbox 联合验收仍受本机安全测试库与 Docker 可用性限制。
