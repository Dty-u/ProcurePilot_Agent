# M8 Checkpoint 与用户 Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使用独立 Agent MySQL 数据库持久化 checkpoint、用户偏好、恢复元数据和展示消息，实现安全的中断恢复与跨会话偏好。

**Architecture:** 采购业务 MySQL 继续作为业务事实库；Agent 状态使用另一个 MySQL 数据库。Checkpoint 以 thread_id 恢复执行，Store 以 user_id 隔离偏好，Resume 和展示消息使用独立表，四者不互相替代。

**Tech Stack:** LangGraph、AIOMySQLSaver、AIOMySQLStore、aiomysql、Pydantic、pytest

---

## 前置条件与版本确认

- M7 Agent 契约通过。
- 使用 `langgraph-checkpoint-mysql==3.0.0` 的 `AIOMySQLSaver`；该实现要求 MySQL >= 8.0.19。
- Agent 状态数据库必须与采购业务数据库分离；Checkpoint、Store、Resume 和展示历史使用不同表。

### Task 1: Agent MySQL 生命周期

**Files:**
- Create: `src/agent/persistence.py`
- Test: `src/tests/unit/agent/test_persistence_factory.py`

Settings 配置独立 Agent MySQL DSN。实现异步上下文管理器，负责 Checkpoint 与 Store 连接和关闭；只有明确启用时才执行状态表 setup，模块导入不连接数据库。

测试内存模式、缺少 DSN、setup 失败关闭和资源正常关闭。

### Task 2: Checkpoint 隔离

**Files:**
- Test: `src/tests/integration/agent/test_checkpoint_resume.py`

使用 `AIOMySQLSaver` 编译 Agent。Runnable config 至少包含 thread_id，并通过应用层维护 thread 所属 user_id。测试同一 thread 中断后重建应用实例仍可恢复；不存在的 thread 返回明确错误；其他用户即使知道 thread_id 也不能读取或恢复。

### Task 3: 用户偏好 Store

**Files:**
- Create: `src/agent/memory/__init__.py`
- Create: `src/agent/memory/preferences.py`
- Test: `src/tests/integration/agent/test_user_memory.py`

偏好 Schema 仅包含 preferred_output、preferred_chart_type、preferred_currency、preferred_language、有限 recent_suppliers 和 recent_queries。namespace 以不可伪造的 user_id 建立；不保存角色、凭据、个人敏感属性、完整聊天或业务主数据。

自动更新采用白名单字段、长度上限和数量上限。一次 Store batch 出错时不影响业务写结果，但必须记录告警；关键身份隔离错误必须失败关闭。

### Task 4: 展示消息 Repository

**Files:**
- Create: `src/api_view/__init__.py`
- Create: `src/api_view/message_repository.py`
- Modify: `pyproject.toml`
- Test: `src/tests/integration/api_view/test_message_repository.py`

`api_view` 是 `src/` 下与 `procurepilot`、`agent` 并列的独立 Python 包。将其加入 wheel 包清单；不得创建 `src/procurepilot/api_view/`。

消息主键为 thread_id + message_id，保存角色、脱敏内容、事件时间和 source。不得保存 LangGraph 原始 state、工具完整敏感结果和审批 Token。删除展示历史不删除 checkpoint、Memory、订单或审计。

### Task 5: 安全 Resume Gateway

**Files:**
- Create: `src/agent/resume_service.py`
- Test: `src/tests/security/test_resume_isolation.py`

恢复请求必须验证当前用户、thread_id、一次性 interrupt_id、允许动作和参数摘要。消费 interrupt_id 使用原子状态变更，重放返回冲突。恢复数据只允许 supplement 或 decisions 的规定结构，未知字段拒绝。

覆盖跨用户访问、篡改 payload、重复 resume、过期中断、线程存在但无中断和删除展示历史后的恢复。

### Task 6: 门禁和文档

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest src/tests/integration/agent src/tests/integration/api_view src/tests/security/test_resume_isolation.py -v
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src
git diff --check
```

同步 `wiki/数据模型.md` 和 `wiki/Agent运行机制.md`，明确 checkpoint、展示历史、Memory、MySQL 和 Sandbox 的主键、生命周期与读写路径。

**完成标准：** 重启后可恢复合法中断，跨用户和重放全部被拒绝，三类 Agent 状态数据保持边界独立。

**建议提交：** `feat: 持久化隔离的智能体状态与用户记忆`

## 实施状态（2026-09-14）

M8 已按当前锁定依赖完成：

- 使用 `AIOMySQLSaver` 持久化主 Agent 和订单 HITL Checkpoint；提供只允许专用测试库运行的
  重启恢复集成测试。
- 使用独立 `AIOMySQLStore` 保存 thread 所有权和按可信 `user_id` 隔离的白名单用户偏好。
- 新增独立展示消息 Repository，只保存脱敏后的必要字段；删除展示历史不影响 Checkpoint、
  Memory 或待恢复中断。
- 新增安全 Resume Gateway，验证用户、thread、一次性 interrupt、订单动作、resume 类型、
  参数摘要和有效期；并发重放只有一次成功。
- Agent MySQL 数据库必须与业务数据库分离；Store、Resume 和展示历史使用独立表，模块导入时
  不连接数据库。
- 状态表 `setup()` 默认关闭，只有显式设置 `AGENT_CHECKPOINT_AUTO_SETUP=true` 才执行
  Checkpoint/Store 建表升级及 Resume/展示历史建表。

M8 没有实现 M9 的 OpenSandbox/Skills，也没有实现 M10 的 FastAPI、SSE、生产鉴权或 HTTP
Resume 路由。此次按用户规则未执行 Git commit 或 push。
