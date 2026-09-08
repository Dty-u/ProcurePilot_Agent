# Agent 运行机制

## 路由规则

| 意图 | 处理者 |
| --- | --- |
| 分析、对比、报告、建议、评估、行情、比价、筛选 | `procurement-analyst` |
| 下单、创建、修改、取消、订单状态 | `procurement-order` |
| 问候、通用问答、受控技能管理 | 主 Agent |

主 Agent 只负责路由、委派和汇总。委派消息包含任务目标、原始需求、用户身份作用域、必要偏好和输出要求，不传递密钥或无关对话。

## 分析子 Agent

```text
按需读取采购 Skills
→ MCP 查询 Python 业务数据和允许的外部报价
→ OpenSandbox 中执行分析
→ 生成关键图表和 Markdown 报告
→ 返回结论、证据、风险、建议和产物引用
```

分析过程与大工具输出留在子 Agent/沙箱，主 Agent 只接收结构化结果。

## 订单子 Agent

```text
提取候选字段 → 查询并校验
→ request_order_info 补充缺失字段
→ 展示完整操作摘要
→ interrupt_on 最终审批
→ approve 后写入，reject 后终止
```

模型不得猜测关键字段，不得自行批准，不得通过自然语言伪造成功。

## 中间件

1. `ContextInjectionMiddleware`：注入最小用户上下文。
2. `SkillsSyncMiddleware`：同步本地受信 Skills。
3. `UserSkillsRestoreMiddleware`：恢复已审核 Skills。
4. `SummarizationToolMiddleware`：压缩长上下文和大型工具结果。
5. `MemoryUpdateMiddleware`：更新有限的用户近期记录。
6. `ModelCallLimitMiddleware`：限制模型调用，建议上限 50。
7. `ToolCallLimitMiddleware`：限制工具调用，建议上限 200。

## Backend 与生命周期

`/memories/` 路由到按 `user_id` 隔离的 StoreBackend，`/persisted-skills/` 路由到 Skill Store，其余文件进入 OpenSandbox。业务主数据不使用 CompositeBackend。

Agent 不在模块导入时创建。FastAPI `lifespan` 使用异步工厂初始化；同步入口不能在运行中的事件循环里调用 `asyncio.run()`。

Skills 使用渐进式披露，只在需要时读取完整内容。运行时自动下载和执行 Skill 默认关闭，启用前必须经过来源、版本、哈希和人工审核。

