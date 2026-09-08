# M8 Checkpoint 与用户 Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使用独立 SQLite 持久化 Agent checkpoint、用户偏好和展示消息，实现安全的中断恢复与跨会话偏好。

**Architecture:** MySQL 继续作为业务事实库；SQLite Agent 状态库与业务库物理分离。Checkpoint 以 thread_id 恢复执行，Store 以 user_id 隔离偏好，展示消息使用独立 Repository，三者不互相替代。

**Tech Stack:** LangGraph AsyncSqliteSaver、AsyncSqliteStore、aiosqlite、Pydantic、pytest

---

## 前置条件与版本确认

- M7 Agent 契约通过。
- 使用固定环境实际锁定的 `langgraph-checkpoint-sqlite` API；编码前运行 import/签名探针。
- SQLite 是单进程 MVP 存储，不承诺多实例并发。

### Task 1: 存储路径和生命周期

**Files:**
- Create: `src/procurepilot/agent/persistence.py`
- Test: `tests/unit/agent/test_persistence_factory.py`

Settings 分别配置 checkpoint、store 和 display history 路径，默认位于应用数据目录而非源码目录。路径必须规范化并限制在配置根目录内。实现异步上下文管理器，负责连接、setup 和关闭；模块导入不打开文件。

测试内存模式、目录穿越拒绝、setup 失败关闭和资源正常关闭。

### Task 2: Checkpoint 隔离

**Files:**
- Test: `tests/integration/agent/test_checkpoint_resume.py`

使用 `AsyncSqliteSaver` 编译 Agent。Runnable config 至少包含 thread_id，并通过应用层维护 thread 所属 user_id。测试同一 thread 中断后重建应用实例仍可恢复；不存在的 thread 返回明确错误；其他用户即使知道 thread_id 也不能读取或恢复。

### Task 3: 用户偏好 Store

**Files:**
- Create: `src/procurepilot/agent/memory/preferences.py`
- Test: `tests/integration/agent/test_user_memory.py`

偏好 Schema 仅包含 preferred_output、preferred_chart_type、preferred_currency、preferred_language、有限 recent_suppliers 和 recent_queries。namespace 以不可伪造的 user_id 建立；不保存角色、凭据、个人敏感属性、完整聊天或业务主数据。

自动更新采用白名单字段、长度上限和数量上限。一次 Store batch 出错时不影响业务写结果，但必须记录告警；关键身份隔离错误必须失败关闭。

### Task 4: 展示消息 Repository

**Files:**
- Create: `src/procurepilot/api_view/message_repository.py`
- Test: `tests/integration/api_view/test_message_repository.py`

消息主键为 thread_id + message_id，保存角色、脱敏内容、事件时间和 source。不得保存 LangGraph 原始 state、工具完整敏感结果和审批 Token。删除展示历史不删除 checkpoint、Memory、订单或审计。

### Task 5: 安全 Resume Gateway

**Files:**
- Create: `src/procurepilot/agent/resume_service.py`
- Test: `tests/security/test_resume_isolation.py`

恢复请求必须验证当前用户、thread_id、一次性 interrupt_id、允许动作和参数摘要。消费 interrupt_id 使用原子状态变更，重放返回冲突。恢复数据只允许 supplement 或 decisions 的规定结构，未知字段拒绝。

覆盖跨用户访问、篡改 payload、重复 resume、过期中断、线程存在但无中断和删除展示历史后的恢复。

### Task 6: 门禁和文档

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest tests/integration/agent tests/integration/api_view tests/security/test_resume_isolation.py -v
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src tests
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src tests
git diff --check
```

同步 `wiki/数据模型.md` 和 `wiki/Agent运行机制.md`，明确 checkpoint、展示历史、Memory、MySQL 和 Sandbox 的主键、生命周期与读写路径。

**完成标准：** 重启后可恢复合法中断，跨用户和重放全部被拒绝，三类 Agent 状态数据保持边界独立。

**建议提交：** `feat: persist isolated agent state and user memory`

