# M7 Multi-Agent 编排 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使用 DeepAgents 0.4.12 组装主 Agent、采购分析子 Agent 和采购订单子 Agent，并强制执行最小工具权限。

**Architecture:** 主 Agent 是协调器，只路由和汇总；分析子 Agent 只读；订单子 Agent 负责收集参数并调用受审批保护的写工具。所有 Agent 由异步工厂在应用生命周期中创建，子 Agent 通过结构化结果压缩上下文。

**Tech Stack:** DeepAgents 0.4.12、LangChain、LangGraph、Pydantic、pytest

---

## 前置条件

- M5 分析 Agent 和 M6 安全写入均通过。
- 开始编码前，用固定解释器执行 `inspect.signature(create_deep_agent)` 并阅读已安装 0.4.12 的 `graph.py` 与 subagent 类型；计划中的调用必须以安装包为准。

### Task 1: ProcurementContext

**Files:**
- Create: `src/procurepilot/agent/context.py`
- Test: `tests/unit/agent/test_context.py`

定义最小上下文：user_id、username、thread_id、trace_id、roles、language、timezone。禁止包含 API Key、DSN、完整历史和原始身份 Token。上下文必须由 API 鉴权层创建，Agent 输入不能覆盖。

### Task 2: 工具清单和权限断言

**Files:**
- Create: `src/procurepilot/agent/toolsets.py`
- Test: `tests/contract/agent/test_tool_permissions.py`

固定工具集：

```text
main: task/委派和必要的非业务工具
procurement-analyst: 六个只读采购工具
procurement-order: 实体查询、request_order_info、order_create/update/cancel
```

不得通过“默认继承全部工具”给子 Agent 授权。测试直接枚举已编译 Agent/配置中的工具名，证明分析 Agent 看不到写工具，主 Agent 不能直接写订单。

### Task 3: 订单子 Agent

**Files:**
- Create: `src/procurepilot/agent/order/agent.py`
- Create: `src/procurepilot/agent/order/prompt.py`
- Test: `tests/contract/agent/test_order_agent.py`

Prompt 固定流程：提取候选字段 → 查询真实实体 → 业务预校验 → 缺字段 interrupt → 显示完整摘要 → HITL 审批 → 受控写工具。禁止根据名称猜 ID、根据用户自然语言伪造审批、绕过 version 或宣称未返回的订单号。

### Task 4: 主 Agent 和委派结构

**Files:**
- Create: `src/procurepilot/agent/main_agent.py`
- Create: `src/procurepilot/agent/prompts.py`
- Test: `tests/contract/agent/test_routing.py`

实现 `create_main_agent(...)` 异步工厂，并向 `create_deep_agent` 显式传入 model、tools、subagents、system_prompt、checkpointer、store、backend、interrupt_on 和 middleware。

路由规则：分析/对比/报告/建议/评估/行情/比价/筛选 → analyst；下单/创建/修改/取消/订单状态 → order；问候和受控通用问答 → main。混合请求先拆分只读分析，再由用户明确发起写操作，禁止分析推荐自动转化为订单。

委派载荷只包含任务目标、原始需求、最小身份作用域、必要偏好和输出要求。子 Agent 返回结构化结果，主 Agent 不接收完整中间工具日志。

### Task 5: 中间件和调用上限

**Files:**
- Create: `src/procurepilot/agent/middleware.py`
- Test: `tests/contract/agent/test_call_limits.py`

配置 ContextInjection、ModelCallLimit=50、ToolCallLimit=200。M7 只加入已需要且可测试的中间件；Skills、Sandbox 和 Memory 延后至 M8/M9。限制命中后停止运行并返回稳定错误，不尝试无限自我修复。

### Task 6: Agent 契约验收

测试 Fake Model 场景：正确路由、歧义澄清、混合读写拆分、子 Agent 工具失败、调用上限、Prompt Injection、分析 Agent 尝试写工具被拒绝、订单 Agent 无审批无法写入。

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest tests/unit/agent tests/contract/agent -v
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src tests
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src tests
git diff --check
```

同步 `wiki/Agent运行机制.md` 和 `rules/工程架构.md`，记录实际工具边界和初始化路径。

**完成标准：** 三个 Agent 的路由、权限、错误传播和调用上限都有确定性契约测试。

**建议提交：** `feat: assemble constrained procurement multi-agent`

