# Agent 运行机制

M7 已使用项目锁定的 `DeepAgents==0.4.12` 组装主 Agent、分析子 Agent和订单子 Agent。M8 提供 MySQL Checkpoint/Store、展示历史和 Resume Gateway；M9 已接入 OpenSandbox Backend 与审核 Skill；M10 已接入 FastAPI、SSE、HTTP 恢复和历史路由。

当前真实初始化链路为：

```text
可信 ProcurementContext
→ MCP Client（绑定同一调用者上下文）
→ 六个分析 MCP 工具 + 八个订单工具
→ 创建请求级 OpenSandbox，同步本地白名单 Skill
→ create_main_agent()
→ DeepAgents 主 Agent
```

`agent/application.py` 负责上述装配，`agent/cli_demo.py` 是当前可运行入口。测试不再仅用同名占位工具证明图能够编译。

两个子 Agent 统一位于 `agent/subagents/`。主 Agent 启动时从
`agent/subagents/configs/procurement_analyst.yaml` 与
`agent/subagents/configs/procurement_order.yaml` 加载名称、描述、调用上限和最小工具清单，
再由 `loader.py` 按工具名称解析为可调用对象；缺少或重复声明的工具会使初始化失败。YAML
只描述配置，实际 Agent 继续由 `create_deep_agent()` 编译。

主 Agent、两个子 Agent、子 Agent 描述、MCP 服务说明和业务工具描述均使用中文提示词；
工具名、结构化字段名和稳定错误码继续保留英文，避免破坏程序契约。

## 路由规则

| 意图 | 处理者 |
| --- | --- |
| 分析、对比、报告、建议、评估、行情、比价、筛选 | `procurement-analyst` |
| 下单、创建、修改、取消、订单状态 | `procurement-order` |
| 问候、通用问答、受控技能管理 | 主 Agent |

主 Agent 只负责路由、委派和汇总。委派消息包含任务目标、原始需求、用户身份作用域、必要偏好和输出要求，不传递密钥或无关对话。

## 分析子 Agent

### M5 已实现

采购分析 Agent 通过异步工厂创建，模型由 `create_chat_model(settings)` 显式注入，不在
模块导入时初始化客户端。当前 Agent 通过 `create_deep_agent()` 编译，并且只注册以下六个
采购业务工具：

- `supplier_query`
- `part_query`
- `part_by_supplier`
- `quotation_query`
- `inventory_warning`
- `order_search_details`

工具业务参数不包含 `user_id` 和 `roles`；身份、角色和 `trace_id` 从可信
`ProcurementContext` 注入，并与已认证 MCP 会话绑定。MCP 失败信封会转换成明确的工具
错误，不能伪装为空列表。

分析输入明确包含物料、数量、单位、币种和有效时间。输出为经过 Pydantic 校验的
`AnalysisResult`，包含摘要、候选、推荐、证据、风险、限制和产物引用。每个候选必须保留
`supplier_id` 与 `quotation_id`，并与成功的 `quotation_query` 返回逐字段核对；没有成功
报价证据、模型结构非法或候选无法溯源时返回稳定失败，不透传模型的未校验文本。

DeepAgents 0.4.12 会固定加入 `task`、todo 和文件工具；FastAPI 真实装配为主 Agent 和两个子 Agent 注入同一请求级 `DeepAgentsSandboxBackend`，文件与 Shell 只委托 OpenSandbox。采购权限断言只把
上述六个工具视为业务工具，框架内置工具不能访问订单写接口或替代报价证据。

单次运行默认限制 50 次模型调用和 200 次工具调用，超过上限后停止并返回
`CALL_LIMIT_EXCEEDED`。M5 不注册订单写工具、宿主机文件、Shell、浏览器或 Sandbox。

当配置的官方模型地址为 `api.deepseek.com` 时，模型工厂会关闭 DeepSeek
thinking 模式。原因是当前分析 Agent 的 `ToolStrategy` 需要使用 `tool_choice`
选择查询工具或 `AnalysisResult` 结果工具，而 DeepSeek V4 thinking 模式会拒绝
该参数。其他 OpenAI-compatible 地址不会被修改。

分析 Agent、订单 Agent 和主 Agent 现在都通过项目锁定的
`DeepAgents==0.4.12 create_deep_agent()` 编译。LangChain 仅作为 DeepAgents 公开依赖，
提供 `BaseChatModel`、`BaseTool`、结构化输出和 Middleware 类型；项目代码不再直接调用
LangChain `create_agent()` 创建智能体。

### M9 分析产物

```text
按需读取采购 Skills
→ MCP 查询 Python 业务数据和允许的外部报价
→ OpenSandbox 中执行分析
→ 生成关键图表和 Markdown 报告
→ 返回结论、证据、风险、建议和产物引用
```

分析过程与大工具输出留在子 Agent/沙箱，主 Agent 只接收结构化结果。`supplier-comparison` Skill 仅接收已验证报价 JSON，生成 analysis JSON、CSV、PNG 和 Markdown，不联网、不读凭据、不写业务数据。

## 订单子 Agent

```text
提取候选字段 → 查询并校验
→ request_order_info 补充缺失字段
→ 展示完整操作摘要
→ interrupt_on 最终审批
→ approve 后写入，reject 后终止
```

模型不得猜测关键字段，不得自行批准，不得通过自然语言伪造成功。

订单子 Agent 的工具清单固定为 `supplier_query`、`part_query`、`quotation_query`、
`order_search_details`、`request_order_info`、`order_create`、`order_update` 和
`order_cancel`。除本地中断工具 `request_order_info` 外，查询和写入全部通过 MCP Client 调用
MCP Server；Agent 工具不依赖 Business Service、Repository 或数据库。三个写工具只接收 operation/approval/idempotency 引用及必要的
`expected_version`；供应商、物料、数量、币种和报价等真实业务参数始终从已保存 operation
读取。主 Agent 与分析 Agent 均看不到写工具。

`user_id`、`roles`、`thread_id`、`trace_id` 在应用装配时从可信 `ProcurementContext` 绑定，
不出现在模型工具参数中。MCP 的失败信封会转为 `ToolException`，三个写工具每次只调用一次
Gateway，不做自动重试。即使 HITL 放行，MCP Server 后的 `OrderService` 仍会重新校验审批、
幂等和乐观锁，HITL 不是业务授权的替代品。

## 中间件

当前启用且已有测试的中间件只有：

1. `middlewares/context_injection.py`：没有可信 `ProcurementContext` 时失败关闭。
2. `middlewares/model_call_limit.py`：单次模型调用最多 50 次，命中后抛出限制错误。
3. `middlewares/tool_call_limit.py`：单次工具调用最多 200 次，命中后停止。
4. 订单子 Agent 的 HITL middleware：三种写工具调用前暂停。

前三项由 `agent.middlewares.create_runtime_middleware()` 按上述顺序装配。M8 的偏好通过
显式 `UserPreferenceRepository` 读写，不把完整聊天自动总结成 Memory，也没有引入一个
未经约束的模型写 Memory 中间件。Skill 只从本地审核白名单同步，禁止运行时下载和自我修改。

## Backend 与生命周期

M8 的 `open_agent_persistence()` 在显式生命周期内打开 `AIOMySQLSaver` 和
`AIOMySQLStore`，退出时可靠关闭。主 Agent 和订单子 Agent 使用独立 Agent MySQL 数据库中的
Checkpoint，订单 HITL 可以在 Agent 重建后恢复；MySQL Store 保存 thread 所有权和按用户
隔离的偏好。Agent 数据库不得与采购业务数据库相同。

Checkpoint 表的首次建表或包版本迁移默认关闭；只有运维明确设置
`AGENT_CHECKPOINT_AUTO_SETUP=true` 时才初始化 Checkpoint、Store、Resume 和展示历史表。
普通启动只打开已有表，避免应用进程在不知情时改变数据库结构。

安全恢复固定为：

```text
可信用户上下文
→ 校验 thread_id 与 interrupt_id
→ 校验 action、resume kind 与参数摘要 SHA-256
→ 校验有效期
→ 独立 Resume MySQL 表原子消费 interrupt_id
→ 生成 supplement 或 approve/reject 的 LangGraph resume 数据
```

并发或重复消费只有一次成功。订单 HITL 只允许 `approve` 与 `reject`，不允许在审批阶段
编辑工具参数或用 `respond` 伪装执行结果。M10 HTTP 路由先通过 Resume Gateway 原子消费，再由服务端构造 `Command(resume=...)`。

FastAPI lifespan 打开模型、Agent MySQL Checkpoint/Store、Resume 和展示消息仓储；每个请求再创建绑定当前身份的 MCP Client 和独立 Sandbox，结束时销毁。这避免共享 Agent 泄漏身份或沙箱文件。模块导入本身不会连接外部系统。
