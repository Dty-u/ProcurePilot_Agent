# 1、手撕OpenClaw并且基于Harness架构的ERP智能采购助手项目

## 项目准备：

- Java的ERP系统

- 模拟的供应商网站

- 魔塔社区免费的可视化分析工具

- DeepAgents==0\.4\.12版本/ 先不要更新到最新的DeepAgents

    s

## 1、项目目录架构

```Plain Text
src/
├── agent/                              # Agent 核心
│   ├── main_agent.py                   # 主 Agent 入口（11阶段初始化流水线）
│   ├── config.py                       # 全局配置（模型/沙箱/MongoDB/路径/Store）
│   ├── schema.py                       # 数据结构（ProcurementContext / SSE事件模型 / API模型）
│   ├── env_utils.py                    # 环境变量读取
│   ├── middleware_config.py            # 子 Agent 中间件工厂
│   │
│   ├── memory/
│   │   ├── AGENTS.md                   # 主 Agent 通用行为准则（沙箱 /AGENTS.md）
│   │   └── prompts.py                  # 主 Agent system_prompt（精简版协调者角色）
│   │
│   ├── backends/
│   │   ├── sandbox_setup.py            # 沙箱创建 + 基础文件播种（seed）
│   │   └── custom_opensandbox.py       # OpenSandboxBackend 自定义封装
│   │
│   ├── middlewares/                    # 中间件栈（7个，按主 Agent 注入顺序）
│   │   ├── context_injection.py        # 1. 注入用户上下文到 system prompt
│   │   ├── skills_sync.py              # 2. 本地技能 → 沙箱同步（增量）
│   │   ├── user_skills_restore.py      # 3. StoreBackend → 沙箱恢复持久化技能
│   │   ├── tools_summarization.py      # 4. SummarizationToolMiddleware 封装
│   │   └── memory_update.py            # 5. 自动更新 recent_suppliers / recent_queries
│   │
│   ├── subagents/
│   │   ├── loader.py                   # YAML 配置加载 + 工具名称匹配解析
│   │   └── configs/
│   │       ├── procurement_analyst.yaml # 分析子 Agent 配置
│   │       └── procurement_order.yaml  # 订单子 Agent 配置
│   │
│   └── tools/
│       ├── mcp_client.py               # MCP 多服务器连接 + 工具按前缀分组
│       ├── chart_generator.py          # 26种图→1个 generate_visualization 入口
│       ├── web_search.py               # 智谱搜狗 Web 搜索
│       ├── hitl_tools.py               # request_order_info（数据补充中断）
│       ├── assign_skill.py             # 技能分配（复制+StoreBackend持久化+清理）
│       └── download_sandbox_file.py    # 沙箱文件下载到本地
│
├── skills/                             # 技能资源（本地 → 沙箱同步）
│   ├── main/skill-management/          # 技能生命周期管理
│   └── procurement/
│       ├── chart_params.md             # 26种图表完整参数参考
│       ├── procurement-analysis/SKILL.md  # 分析流程操作手册（5步）
│       ├── supplier-price-urls/        # 供应商报价URL映射表
│       └── web-scraper/                # 网页抓取（直接HTTP+HTML→MD）
│
├── api_view/                           # FastAPI Web层
│   ├── web_main.py                     # FastAPI app 入口（lifespan/路由/CORS）
│   ├── agent_loader.py                 # Agent 懒加载 + MongoDB 管理
│   ├── web_config.py                   # API 元信息
│   └── api/
│       ├── chat.py                     # SSE 流式对话 + 中断检测 + resume 端点
│       └── history.py                  # 历史会话管理（MongoDB CRUD）
│
├── mcp_server/                         # MCP Server（ERP 业务接口代理）
│   ├── server_main.py                  # MCP 服务入口（端口8000）
│   └── tools/
│       ├── suppliers_tools.py          # supplier_query / supplier_*
│       ├── parts_tools.py              # part_query / part_search / part_by_supplier
│       ├── order_tools.py              # order_create / order_update / order_search_details
│       └── inventory_tools.py          # inventory_warning
│
└── test/
    └── agent_test.py                   # 终端测试脚本
```

## 2、Multi\-Agent的描述

### 一、主 Agent（Orchestrator）

**委派规则：**

- 触发"分析/对比/报告/建议/评估/行情/比价/筛选" → `procurement-analyst`

- 触发"下单/创建订单/修改/更新/取消/订单状态" → `procurement-order`

- 问候/知识问答/技能管理 → 主Agent自行处理

### 二、procurement\-analyst（采购分析子Agent）

**分析工作流（5阶段）：**

```Plain Text
1. ls /skills/procurement/ → 扫描可用技能
2. MCP工具获取ERP数据 + supplier-price-urls找外部URL + web-content-fetcher爬取报价
3. Python脚本分析 → /data/analysis_result.json
4. generate_visualization → 2-4张关键图表
5. write_file /analysis/report_*.md → 返回结构化摘要+结论+建议
```

---

### 三、procurement\-order（采购订单子Agent）

## 3、核心数据流程

```Plain Text
1. 用户输入 "帮我对摩托车火花塞做供应商比价分析"

2. ContextInjectionMiddleware
   → runtime.context 提取 user_id="laoxiao", username="laoxiao"
   → 注入 SystemMessage: "当前用户 user_id: laoxiao, 偏好文件: /memories/laoxiao/preferences.md"

3. MemoryMiddleware
   → 从沙箱 /AGENTS.md 加载全局准则 → 注入 system prompt

4. Agent 推理
   → 读取 /memories/laoxiao/preferences.md (StoreBackend)
   → 判断: "比价分析" → 委派 procurement-analyst

5. task(procurement-analyst) 委派格式:
   【任务目标】【用户偏好】【分析需求正文】【输出要求】

6. 子 Agent (procurement-analyst) 执行:
   a. ls /skills/procurement/ → 扫描可用技能
   b. supplier_query("火花塞") → MCP → Java后端 → ERP数据
   c. part_by_supplier(supplier_id) → 按供应商查零部件
   d. 技能: 读取 supplier-price-urls/data/url_mapping.yaml
      → 匹配 URL → web-content-fetcher 爬取外部报价
   e. Python 分析脚本 → /data/analysis_result.json
   f. generate_visualization("bar", chart_config={...}) → 图表URL
   g. write_file("/analysis/report_20260509.md") → 最终报告

7. 子 Agent → compact_conversation → 返回结构化结果给主 Agent

8. 主 Agent → 组织用户友好回复 → 更新 /memories/laoxiao/preferences.md (如有新偏好)
```

## 4、存储架构（CompositeBackend 分流）

## 5、项目中的自定义中间件

### 一、设计原则总结

1. **读写分离**：ContextInjection（读记忆）↔ MemoryUpdate（写记忆），注入时明确告知 Agent "系统自动维护，你无需手动更新"

2. **三层 skills 同步**：SkillsSync（本地→沙箱）\+ UserSkillsRestore（Store→沙箱）\+ SkillsMiddleware（沙箱→Agent 发现），各管一段

3. **主/子差异化管理**：主 Agent 有全量中间件，analyst 保留摘要，order 只要限制——按需减配

4. **静默失败 \> 崩溃**：ContextInjection 三级降级、SkillsSync 异常捕获、MemoryUpdate 全 try/except——任何中间件挂了都不能拖垮 Agent

```Plain Text
before_agent ──────────────────────────────────────►  after_agent
    │                                                      │
    ▼                                                      ▼
[1] ContextInjection    →  注入用户身份 SystemMessage
[2] SkillsSync          →  同步本地 skills → 沙箱
[3] UserSkillsRestore   →  恢复持久化 skills → 沙箱
[4] SummarizationTool   →  上下文压缩 + compact_conversation 工具
[5] MemoryUpdate        →                                   自动更新用户记忆
[6] ModelCallLimit      →  限制 LLM 调用 ≤ 50 次
[7] ToolCallLimit       →  限制工具调用 ≤ 200 次
```

LangChain `AgentMiddleware` 提供 6 个钩子，项目使用了其中 4 个：

```Plain Text
chat.py:282  agent_loader.agent.astream(...)
                │                                          ← astream() 被调用
                │  ┌─────────────────────────────────┐
                │  │ LangGraph 内部启动：              │
                │  │ 1. 根据 config 恢复 checkpoint    │
                │  │ 2. 初始化 state（含历史消息）      │
                │  │ 3. 构建 runtime.context          │
                │  │                                  │
                │  │ 4. before_agent 钩子触发 ← 这里！  │  ← 在 astream 内部
                │  │    ├─ ContextInjection           │
                │  │    ├─ SkillsSync                 │
                │  │    └─ UserSkillsRestore          │
                │  │                                  │
                │  │ 5. before_model 钩子触发          │
                │  │ 6. LLM 推理                       │
                │  │ 7. 生成第一个 token               │
                │  └─────────────────────────────────┘
                │                                          ← 第一条 chunk yield
chat.py:282  async for chunk in ...:    ← chat.py 收到第一条数据

                      after_agent 钩子                           ← "结束后"
                │      └─ MemoryUpdate 在这里写 Store
                │  astream() 生成器退出                       
chat.py:xxx  # async for 循环结束，代码继续往下走              ← chat.py 继续执行
```



### 二、每个中间件的说明

#### \[1\] ContextInjectionMiddleware `before_agent`

#### \[2\] SkillsSyncMiddleware `before_agent`

#### \[3\] UserSkillsRestoreMiddleware `before_agent`

#### \[4\] SummarizationToolMiddleware `before_model`

#### \[5\] MemoryUpdateMiddleware `after_agent`

**MemoryUpdate 内部流程**：

```Plain Text
after_agent 触发
  │
  ├─ ① 从 runtime.context 获取 user_id
  │
  ├─ ② _is_meaningful_erp_exchange(messages)
  │      ├─ 找最后一条 HumanMessage
  │      ├─ 跳过闲聊（_SKIP_PATTERNS：你好/在吗/你是谁...）
  │      ├─ 检查是否包含 ERP 关键词（供应商/采购/订单/报价...）
  │      └─ 兜底：检查是否有 task（子 Agent）工具调用
  │
  ├─ ③ _extract_ai_summary(messages)
  │      取最后一条 AIMessage 前 300 字符
  │
  ├─ ④ _extract_entities(model, user_msg, ai_summary)
  │      LLM 提取 JSON: {"suppliers": [...], "query": "..."}
  │
  ├─ ⑤ store.aget(namespace, key)
  │      读取 /memories/{user_id}/preferences.md 当前内容
  │
  ├─ ⑥ _merge_preferences(current_lines, new_suppliers, new_query)
  │      解析旧的 recent_suppliers / recent_queries 区块
  │      → 移除旧区块 → 合并新旧 → 去重 → 截断（suppliers ≤ 10, queries ≤ 5）
  │      → 追加到文件末尾
  │
  └─ ⑦ store.aput(namespace, key, file_value)
         写回 StoreBackend
```

#### \[6\] ModelCallLimitMiddleware

#### \[7\] ToolCallLimitMiddleware



## 6、Agent懒加载的设计

### 一、为什么需要懒加载

`create_main_agent()` 内部是 **11 个阶段的初始化流水线**：

```Plain Text
沙箱创建 → MCP 工具加载 → 26→1 工具合并 → 子Agent YAML加载 → 
中间件构建 → create_deep_agent() 编译 StateGraph
```

这个流程涉及网络 I/O（MCP 连接、沙箱 API）和计算（LangGraph 编译），可能耗时 5\-15 秒。如果放在模块 `import` 阶段执行，会导致：

- `import agent.main_agent` 卡死 10 秒

- 模块级别错误无法被 try/except 捕获

- 测试/CLI 每次启动都要等，即使不调用 Agent

懒加载的核心思想：**模块导入时只创建一个空壳，真正使用时才初始化。**



**实际流程时序**

```Plain Text
FastAPI 启动
  │
  ├─ lifespan 事件触发
  │    agent_loader.initialize()
  │      from agent.main_agent import get_agent_async  ← 导入模块
  │      │                                               ← _AgentProxy() 创建（空壳）
  │      │                                               ← 无事件循环，什么都不发生
  │      │
  │      agent = await get_agent_async()                ← 显式异步初始化
  │        ├─ _is_initialized? → False
  │        ├─ await _create_agent()                      ← 11 个阶段，5-15 秒
  │        │    ├─ Phase 1: setup_sandbox()
  │        │    ├─ Phase 2: load_mcp_tools()             ← 连接 MCP 服务器
  │        │    ├─ Phase 3: create_generate_chart_tool()
  │        │    ├─ ...
  │        │    └─ Phase 9: create_deep_agent()          ← 编译 StateGraph
  │        └─ agent._agent = graph
  │
  ├─ HTTP 请求到达
  │    agent.astream(...)                                ← _AgentProxy._agent 已有值
  │                                                      ← __getattr__ → 直接返回 graph
  │                                                      ← 不经过 _ensure_initialized 检测
```

### 二、`_AgentProxy` 的三层设计

```Plain Text
┌─────────────────────────────┐
               │         _AgentProxy()        │
               │         self._agent = None   │  ← 导入时：空壳，0 开销
               └──────────┬──────────────────┘
                          │
            ┌─────────────┼─────────────┐
            ▼                           ▼
    __getattr__("astream")      get_agent_async()
    (透明属性访问)              (显式异步初始化)
            │                           │
            ▼                           ▼
    _ensure_initialized()      await _create_agent()
            │                           │
            ▼                           ▼
    asyncio.run(_create_agent())      self._agent = graph
    self._agent = graph
```

#### 第一层：`getattr` 透明代理（`agent.astream()` 直接用）

```Python
# main_agent.py:297
def __getattr__(self, name):
    return getattr(self._ensure_initialized(), name)
```

任何对 `agent.xxx` 的访问（`.astream()`, `.ainvoke()`, `.aget_state()` 等）都先触发 `_ensure_initialized()`，然后委托给真实的编译后 graph 对象。调用方不需要感知代理的存在：

```Python
# agent_test.py:7
from agent.main_agent import agent   # ← 空壳，不阻塞

# agent_test.py:74  ——  首次访问触发初始化
async for chunk in agent.astream(...):   # ← __getattr__ → 初始化 → 委托
```

#### 第二层：`_ensure_initialized()` 事件循环检测

```Python
# main_agent.py:272-295
def _ensure_initialized(self):
    if self._agent is not None:
        return self._agent           # 已初始化，直接返回

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():        # ← 检测：当前在事件循环中？
            raise RuntimeError(       #    是 → 无法用 asyncio.run()，报错
                "Agent 尚未初始化且当前在事件循环中，"
                "请使用 await get_agent_async() 获取 agent"
            )
    except RuntimeError as e:
        if "Agent 尚未初始化" in str(e):
            raise                     # ← 我们自己的错，往上抛
        # asyncio.get_event_loop() 抛的错（无事件循环）→ 可以安全用 asyncio.run()

    self._agent = asyncio.run(_create_agent())  # ← 同步包装异步创建
    return self._agent
```

这里用了一个**双重 RuntimeError 技巧**：

用代码路径表示：

```Plain Text
场景 A: agent_test.py 控制台
─────────────────────────────
import agent.main_agent    → _AgentProxy() 创建（agent._agent = None）
...其他代码...
asyncio.run(main())        → 事件循环启动
  main() 内:
    agent.astream()        → __getattr__ → _ensure_initialized()
      ├─ _agent 不是 None？→ 不是，继续
      ├─ get_event_loop()  → RuntimeError("no current event loop")  ← 已在事件循环中！
      │   等，这不对...
```

**等一下——这里有一个实际使用中的矛盾。** `agent_test.py` 在 `asyncio.run(main())` 内调用 `agent.astream()`，此时事件循环正在运行。`_ensure_initialized()` 会检测到运行中的循环并抛出 RuntimeError。所以 `agent_test.py` **不能直接用 ****`getattr`**** 路径**——它必须在进入事件循环前调用 `get_agent()` 完成初始化。

#### 第三层：`get_agent()` / `get_agent_async()` 显式初始化

```Python
# main_agent.py:310-325  ——  同步路径
def get_agent():
    global agent
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent._agent
        return agent._ensure_initialized()  # 必须在事件循环外调用
    return agent

# main_agent.py:328-344  ——  异步路径
async def get_agent_async():
    global agent
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent._agent
        agent._agent = await _create_agent()  # 在事件循环内 await
        return agent._agent
    return agent
```

### 三、设计优势

1. **模块导入零开销**：`import agent.main_agent` 瞬间完成，不阻塞

2. **透明代理**：使用者写 `agent.astream()` 和直接持有 graph 对象写 `graph.astream()` 完全一样

3. **双路径兼容**：同步测试脚本用 `get_agent()`，异步服务用 `get_agent_async()`，同一个 `agent` 全局变量

4. **只初始化一次**：`self._agent` 一旦赋值，后续调用全部跳过





## 7、MCP服务器中26\+个工具如何合并

### 一、它解决什么问题

魔塔社区 MCP Server 暴露了 26 个独立的可视化工具：

```Plain Text
generate_bar_chart, generate_line_chart, generate_pie_chart,
generate_scatter_chart, generate_radar_chart, generate_sankey_chart,
generate_area_chart, generate_column_chart, generate_boxplot_chart,
generate_violin_chart, generate_histogram_chart, generate_funnel_chart,
generate_treemap_chart, generate_word_cloud_chart, generate_waterfall_chart,
generate_dual_axes_chart, generate_venn_chart, generate_liquid_chart,
generate_organization_chart, generate_mind_map, generate_fishbone_diagram,
generate_flow_diagram, generate_network_graph,
generate_district_map, generate_pin_map, generate_path_map
```

如果全部直接注入 Agent，工具列表描述会占用大量上下文，每次 LLM 调用都要遍历 26 个工具的 schema。`chart_generator.py` 把这些合并成 **1 个入口**：`generate_visualization(chart_type, chart_config)`，通过 `chart_type` 字符串路由到实际的 MCP 工具。

### 二、工具描述的 token 预算策略

合并后 `generate_visualization` 的工具描述分两部分：

#### 第一部分：工具本体（\~50 tokens）

```Python
# 第 267-277 行
"Generate a data visualization and return the image URL.\n"
"Use this tool to create charts, maps, diagrams, or mind maps for analysis reports.\n"
f"Available chart_type values: {chart_list}\n"
+ _COMPACT_TABLE  # ~800 tokens
+ "\nWhen unsure about the exact fields for chart_config, read "
+ "`/skills/procurement/chart_params.md` first, then call this tool."
```

#### 第二部分：`_COMPACT_TABLE` 速查表（\~800 tokens）

按 6 种数据模式分组，每组列出 chart\_type → data 格式 → 特有参数：

```Plain Text
category-value 模式 ─→ bar, column, pie, funnel, treemap, word_cloud
time-value 模式     ─→ line, area
分布/统计模式       ─→ boxplot, violin, histogram, scatter
多维度/流向/集合    ─→ radar, sankey, venn, waterfall, dual_axes
特殊图表            ─→ liquid, organization, mind_map, fishbone_diagram, flow_diagram, network_graph
地图                ─→ district_map, pin_map, path_map
```

速查表只写 data 格式和**特有**参数（如 `liquid` 的 `percent` 必填、`pie` 的 `innerRadius`）。通用参数（`width`, `height`, `title`, `theme`, `style`）只在表头一句话概括，不逐图重复。

#### 第三部分：完整参数文档（沙箱文件）

速查表装不下的细节（如 `district_map` 的 `subdistricts`/`showAllSubdistricts`/`dataType` 等字段含义、`dual_axes` 的嵌套 `series` 结构示例代码）放入沙箱 `/skills/procurement/chart_params.md`，Agent 不确定时主动 `read_file` 查看。

**设计意图**：工具描述是每次 LLM 调用都加载的，必须短（控制在 \~850 tokens）。完整参数参考只在需要时才加载进上下文。这就是"渐进式披露"在工具参数层面的应用。

### 三、工厂函数 `create_generate_chart_tool()` 的输入输出

```Python
def create_generate_chart_tool(chart_mcp_tools: list):
    """
    Returns:
        (generate_visualization, other_tools) 二元组
        - generate_visualization: 合并后的可视化入口工具
        - other_tools: 未被合并且应保留的独立工具列表
    """
```

调用方从 `load_mcp_tools()` 拿到 `chart_mcp_tools` 后传入，拿到两个产物：

```Python
# main_agent.py:158-160
generate_visualization, extra_mcp_tools = create_generate_chart_tool(chart_mcp_tools)
```

- `generate_visualization` 进入工具池，供主 Agent 和子 Agent 使用

- `extra_mcp_tools`（如 `generate_spreadsheet`）也加入工具池，作为独立工具

### 四、运行时路由：`generate_visualization` 内部

```Python
# 第 325-335 行
@tool
async def generate_visualization(chart_type: str, chart_config: dict) -> str:
    chart_tool = tool_map.get(chart_type)
    if not chart_tool:
        available = ", ".join(sorted(tool_map.keys()))
        return f"Error: Unknown chart type '{chart_type}'. Available types: {available}"
    result = await chart_tool.ainvoke(chart_config)
    return result
```

逻辑极其简单——就是一个字符串查字典 \+ 委托调用：

```Plain Text
Agent 调用: generate_visualization(chart_type="pie", chart_config={"data": [...], "title": "..."})
                │
                ▼
         tool_map["pie"]  →  generate_pie_chart (原始 MCP StructuredTool)
                │
                ▼
         chart_tool.ainvoke({"data": [...], "title": "..."})
                │
                ▼
         魔塔社区 MCP Server → 返回图片 URL
```

### 一个容易被忽略的细节

函数签名写的是 `chart_config: dict`，不是一个 Pydantic 模型。这意味着：

- Agent 传入的参数直接透传给 MCP 工具，不做任何校验

- 如果传错了字段名或格式，错误由魔塔社区 MCP 返回，信息不可控

- 这也是为什么 `chart_params.md` 存在——在没有结构化校验的情况下，只能靠文档引导 Agent 传对参数

### 当前设计的核心机制

```Plain Text
┌─ 魔塔社区 MCP Server ─────────────────────────────┐
│  generate_bar_chart     generate_line_chart         │
│  generate_pie_chart     generate_scatter_chart      │
│  generate_radar_chart   generate_sankey_chart       │
│  ...共 26 个工具                                     │
└──────────────────┬─────────────────────────────────┘
                   │ create_generate_chart_tool() 合并
                   ▼
┌─ 合并入口 ─────────────────────────────────────────┐
│  generate_visualization(chart_type, chart_config)  │
│                                                    │
│  chart_type: "bar" | "line" | "pie" | ... (26种)   │
│  chart_config: {data: [...], title: "...", ...}    │
│                                                    │
│  路由: tool_map[chart_type].ainvoke(chart_config)   │
└──────────────────────┬─────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    工具描述(~800t)  chart_params.md  运行时动态路由
    (每次 LLM 调用)  (沙箱参考文件)   (ainvoke)
```

三个关键设计决策：

### 五、Agent 使用时的实际调用流程

```Plain Text
Agent 收到任务: "对比博世、电装、德尔福的价格，用柱状图展示"

  Step 1: 分析需求 → 柱状图适合类别对比 → chart_type = "bar"
  
  Step 2: 看工具描述中的速查表 → bar 属于 category-value 模式
          → data 格式: [{category, value}]
          → 没有特殊必填参数 → 直接调用，不需要 read_file
  
  Step 3: generate_visualization(
            chart_type="bar",
            chart_config={
              "data": [
                {"category": "博世", "value": 45.5},
                {"category": "电装", "value": 38.2},
                {"category": "德尔福", "value": 52.0}
              ],
              "title": "火花塞供应商价格对比",
              "axisYTitle": "单价 (元)"
            }
          )
  
  Step 4: 返回图片 URL → Agent 展示给用户


Agent 收到任务: "用思维导图梳理采购策略"

  Step 1: 分析 → chart_type = "mind_map"
  
  Step 2: 看速查表 → mind_map 属于"特殊图表"分组
          → data: {name, children: [{name, children: [...]}]}，最大深度3
          → 格式不直观 → 不确定具体字段 → 先 read_file
  
  Step 3: read_file("/skills/procurement/chart_params.md")
          → 看到完整的 data 结构示例，确认格式
  
  Step 4: generate_visualization("mind_map", {...})
```

两种路径：简单图表 Agent 可以凭速查表直接调，复杂图表 Agent 自己判断需要参考文件。这个"自己判断"的能力取决于模型对数据结构的推理——速查表的 `{name, children: [...]}` 语法是否足够清晰。





# 二、项目中具体Harness架构的实现



一个完整的**Agent Harness由几个相互配合的核心能力层构成**，它们共同决定了Agent的行为和性能：

- 任务规划：通过内置的任务清单功能，将复杂目标分解为一系列可执行的子任务，并追踪每一步的执行状态。

- 虚拟文件系统：为Agent提供一个内置的虚拟文件管理系统，支持读写、编辑、搜索等操作，使其能像人类开发者一样进行工作。

- 子Agent委派：主Agent可以创建专门的“子Agent”来执行特定任务，实现任务隔离和上下文压缩。

- 上下文管理：通过文件系统等策略，管理长对话中的Token消耗，防止因上下文溢出而导致性能下降。

- 可插拔中间件：通过一组Hook函数，在模型和工具调用的关键节点注入自定义逻辑，实现缓存、重试、日志、PII检测等增强功能。

- Skills技能系统：将提示词、文档、脚本等打包为可复用的标准模块，为Agent注入特定领域的知识和能力。并做到自我进化。

- 持久化记忆：为Agent提供短期（对话历史）和长期记忆能力，使其能从历史交互中学习。



## 2、项目中Harness架构的核心能力\(一\)：长周期复杂任务的Planning能力

提供 `write_todos` 工具，Agent 可维护结构化任务列表（pending/in\_progress/completed），持久化在 Agent state 中。

**项目实现**：

![image\.png](图片和附件/image%207.png)

## 3、项目中harness架构的核心能力\(二\)：安全的和动态路由的文件系统

**项目实现**：通过 `CompositeBackend` 实现**三层路由文件系统**。

**路由分流效果**：

```Python
backend = lambda rt: CompositeBackend(
    default=sandbox_backend,           # OpenSandbox（临时文件、代码执行）
    routes={
        "/memories/": StoreBackend(    # 用户偏好 → MongoDB 持久化
            runtime=rt,
            namespace=lambda rt: (getattr(rt.runtime.context, 'user_id', 'default_user'),),
        ),
        "/persisted-skills/": StoreBackend(  # 持久化技能 → MongoDB
            runtime=rt,
            namespace=lambda rt: SKILLS_STORE_NAMESPACE,
        ),
    },
)
```

## 4、项目中harness架构的核心能力\(三\)： Subagent的任务委派

主 Agent 拥有 `task` 工具，每次调用创建全新 Agent 实例，独立上下文，执行完返回单个报告。支持并行执行和特殊化配置。

**项目实现**：

**子 Agent 配置加载**：loader\.py

```Plain Text
YAML 配置文件 (configs/*.yaml)
  │ load_subagent_configs()      ← YAML → dict 列表
  │ resolve_subagent_tools()     ← 工具名子串匹配 → 可调用对象
  │ _validate_subagent_config()  ← 必填字段校验
  ▼
```

**两个子 Agent 对比**：

**委派模板**（AGENTS\.md:74\-121）：

主 Agent 的 `AGENTS.md` 为每个子 Agent 定义了结构化的 `task` 调用模板，确保 user\_id/username/偏好 正确传递到子 Agent。



## 5、项目中harness架构的核心能力\(四\)：Context Management — 上下文管理

四种策略——Input context（启动时加载）、Compression（自动 offload \+ summarization）、Isolation（子 Agent 隔离）、Long\-term memory（跨线程持久化）。

**项目实现**：

#### a\. Input Context

#### b\. Compression

#### c\. Isolation（子 Agent 上下文隔离）

analyst 执行 5 步分析流程时会产生大量中间结果（MCP 返回的供应商/零部件 JSON、Python 脚本输出、图表生成参数等），全部隔离在子 Agent 自己的上下文窗口中。主 Agent 只收到最终的结构化报告。

#### d\. Long\-term Memory



## 6、项目中harness架构的核心能力\(五\)：Skills — 渐进式技能系统（自我进化）

遵循 Agent Skills 标准，每个技能是含 `SKILL.md` 的目录，支持渐进式披露——启动时只读 frontmatter，需要时再加载完整内容。

**项目实现**：

#### Skills自我进化（4 阶段）

```Plain Text
┌─ 阶段1: 同步到沙箱 ────────────────────────────────┐
│ SkillsSyncMiddleware (增量) + _seed_files() (首次)  │
│ src/skills/ → /skills/{scope}/                     │
└────────────────────────────────────────────────────┘
  │
  ▼
┌─ 阶段2: 渐进式发现 ───────────────────────────────┐
│ Agent 启动时 ls /skills/procurement/              │
│ 看到所有 SKILL.md 的 frontmatter                   │
│ 需要时才 read_file 加载完整内容                     │
└────────────────────────────────────────────────────┘
  │
  ▼
┌─ 阶段3: **运行时根据需要自动创建/下载 新Skill**─────────────────────────┐
│ skill-management 技能                              │
│ execute("python download_skill.py '{url}'")        │
│ → 解压到 /skills/main/{skill_name}/               │
│ → 测试验证                                        │
└────────────────────────────────────────────────────┘
  │
  ▼
┌─ 阶段4: 分配与持久化 ─────────────────────────────┐
│ assign_skill(skill_name, agent_name)               │
│ → 复制到 /skills/{scope}/ (子Agent时)             │
│ → store.aput() 持久化到 StoreBackend              │
│ → UserSkillsRestoreMiddleware 恢复（下次沙箱创建时）│
│ → 清理压缩包                                       │
└────────────────────────────────────────────────────┘
```

#### 基于SkillsSyncMiddleware发现链

```Plain Text
yaml system_prompt: "ls /skills/procurement/ 扫描可用技能"
  → 返回: chart_params.md, procurement-analysis/, supplier-price-urls/, web-scraper/
  → read_file("procurement-analysis/SKILL.md") 加载操作手册
  → 按流程激活各技能
```





## 7、项目中harness架构的核心能力\(六\)： Human\-in\-the\-Loop — 人工介入

通过 `interrupt_on` 参数选择性地在工具调用前暂停，等待人工审批或修改。

**项目实现**：**双层中断体系**。

```Plain Text
第1层: 数据补充 (tool-internal interrupt)
  request_order_info 工具内部调用 interrupt()
  ├─ 触发时机: Schema校验发现必填字段缺失
  ├─ 恢复格式: {"supplement": "自由文本补充信息"}
  └─ 循环: 校验→补充→解析→校验...直到完整

第2层: 最终审批 (interrupt_on 配置)
  order_create / order_update 的 interrupt_on 配置
  ├─ 触发时机: 数据完整，准备执行
  ├─ 恢复格式: {"decisions": [{"type": "approve"|"reject"}]}
  └─ 特性: approve → 执行 / reject → 取消
```

**代码位置**：

**两层中断互不干扰的原因**：`request_order_info` 不在 `interrupt_on` 列表中，不会被 HITL 中间件拦截。两者是**顺序关系**——先补齐数据，再审批执行。



## 8、项目中harness架构的核心能力\(七\)：Memory — 用户偏好记忆管理

**项目实现**：以用户作用域来管理Memory

#### 记忆层次

```Plain Text

┌─ 用户层（读写，跨会话持久化）──────────────────────┐
│ /memories/{user_id}/preferences.md                 │
│ 来源: StoreBackend → MongoDB                      │
│ 内容: preferred_output, preferred_chart_type,      │
│       preferred_currency, preferred_language,      │
│       recent_suppliers, recent_queries             │
│ 加载: 每轮对话前 Agent 主动 read_file             │
│ 更新: Agent 手动 edit_file（偏好变更）             │
│       + MemoryUpdateMiddleware 自动维护            │
│         (recent_suppliers + recent_queries)        │
└───────────────────────────────────────────────────┘
```

#### 记忆更新流程

```Plain Text
【手动路径】用户说"以后都用饼图"
  → Agent edit_file /memories/{user_id}/preferences.md
  → 更新 preferred_chart_type: pie

【自动路径】对话结束后
  → MemoryUpdateMiddleware.aafter_agent()
  → LLM 提取 {suppliers: [...], query: "..."}
  → store.aput() 写入 StoreBackend
  → 跨会话保留
```



## 9、项目的最大安全问题： 基于OpenSandbox来解决

OpenSandbox 就是这个项目的**唯一安全边界**。所有 Agent 行为——运行 Python 脚本、执行 Shell 命令、读写文件、下载技能、爬取网页——全部发生在这个容器内部。**OpenSandbox 的配置决定了这道墙有多厚。**



### 综合风险评估



**OpenSandbox 在这里扮演的角色**：它是最后的兜底线。即使Skills全部失守——恶意技能被下载、解压、恶意代码、文件操作——第 5 阶段执行时，恶意代码仍然被关在容器里。**容器的网络策略决定了恶意代码能造成多大的外部影响。**

### Sandbox 做边界定义：墙内 vs 墙外

```Plain Text
┌──────────────────────────────────────────────────────┐
│                    宿主机 (Windows)                    │
│                                                      │
│     FastAPI（Agent服务器）   MongoDB   MCP Server               │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │          OpenSandbox 容器 (Linux)               │  │
│  │                                                │  │
│  │   /skills/        /data/       /analysis/      │  │
│  │   /memories/      /AGENTS.md   /workspace/     │  │
│  │                                                │  │
│  │   Python，Go，Java，Nodejs 环境                              │  │
│  │   execute("任意命令") → 在这里运行               │  │
│  │   web-scraper → 从这里发出 HTTP 请求            │  │
│  │   技能脚本 → 在这里被调用                        │  │
│  │                                                │  │
│  │   网络出口 ──────────────────────────────→ ???  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### OpenSandbox 防护了三件事：



# 三、基于SSE事件流的完整的前后端

## 1、架构概览：三文件分工

```Plain Text
api_view/api/
├── chat.py      ★ 核心：SSE 流式对话 + 中断检测 + 中断恢复 + 展示消息持久化
├── history.py   ← 历史会话列表 / 消息查询 / 会话删除
└── agent_loader.py (上层) ← Agent 单例 / MongoDB 连接 / 展示消息存取
```

**整体数据流**

```Plain Text
前端 (浏览器)                       后端 (FastAPI)                     LangGraph Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

① POST /api/chat/stream
   {message, thread_id?, user_id?}
        ──────────────────────────→
                                     ② stream_chat_response()
                                        ├─ agent_loader.get_agent_for_user(user_id)
                                        ├─ agent_loader.create_config(thread_id, user_id)
                                        ├─ 构建 input:
                                        │    初始: {"messages": [{"role":"user",...}]}
                                        │    恢复: Command(resume=resume_data)
                                        │
                                     ③ agent_graph.astream(
                                          input, config,
                                          stream_mode=["messages","values"],
                                          subgraphs=True, version="v2"
                                        )
                                        ↓↓↓ 开始流式推送 ↓↓↓
  ←── SSE: token ──────────────────  ←  ④ messages 流: (token, metadata)
  ←── SSE: tool_start ─────────────  ←     token 有 tool_call_chunks → 工具开始
  ←── SSE: tool_args ──────────────  ←     工具参数增量
  ←── SSE: tool_result ────────────  ←     type=="tool" → 工具结果
  ←── SSE: tool_end ───────────────  ←     工具调用结束
  ←── SSE: interrupt ──────────────  ←  ⑤ values 流: chunk["interrupts"]
  ←── SSE: done ───────────────────  ←  ⑥ 流正常结束
```



## 2、SSE的事件流

chat\.py 从头到尾只做一件事：**把 Agent 流式输出转换成前端能消费的 SSE 事件序列**。但它的实现方式体现了项目特色。

#### 一、 双流模式 — 一条连接同时走两路

```Python
# chat.py:281-287
async for chunk in agent_loader.agent.astream(
    input=current_input,
    config=config,
    stream_mode=["messages", "values"],  # ← 双模式
    subgraphs=True,
    version="v2",
):
```

这是整个中断检测机制的基础。常规 SSE 只用 `"messages"` 模式拿 token/tool 事件，但本项目需要检测中断，所以同时开了 `"values"`：

```Plain Text
stream_mode=["messages", "values"]
     │              │
     │              └─→ values 流: 检测 interrupts() 是否触发
     │                   chunk_type == "values" && chunk.get("interrupts")
     │                   先于 messages 处理（代码中 if 在 messages 前面）
     │
     └─→ messages 流: token / tool_call / tool_result
          chunk_type == "messages"
          正常 SSE 事件 (token / tool_start / tool_args / tool_result / tool_end)
```

##### 流 A：`messages` — 内容输出（AIMessage，ToolMessage）

```Plain Text
messages 流产出的 token 类型:

┌─────────────────────────────────────────────────────────┐
│ token.tool_call_chunks 有值                             │  - AIMessage（调用工具的指令，一般没有content）
│   → token.tool_call_chunks[i]["name"] = "web_search"   │  → tool_start 事件
│   → token.tool_call_chunks[i]["args"] = '{"query":...}' │  → tool_args 事件
│                                                         │
│ token.type == "tool"                                    │  # ToolMessage （工具调用后返回的内容）
│   → token.name = "web_search"                          │  → tool_result 事件
│   → token.content = "搜索结果是..."                     │  → tool_end 事件
│                                                         │
│ token.content 是纯文本 (不是 tool, 不是 tool_call_chunks)│
│   → "根据搜索结果，博世刹车片..."                       │  → token 事件
└─────────────────────────────────────────────────────────┘
```

##### 流 B：`values` — 中断检测

```Python
# 中断检测必须在 messages 处理之前执行 (line 296-366)
if chunk_type == "values" and chunk.get("interrupts"):
    for interrupt in chunk["interrupts"]:
        if "action_requests" in interrupt.value:
            → interrupt_type = "hitl_approval"   # 第2层: 审批中断
        elif interrupt.value.get("type") == "order_info_request":
            → interrupt_type = "order_info_supplement"  # 第1层: 数据补充
    → 保存 display_messages 到 MongoDB
    → 发送 done(interrupted=True)
    → return  # 停止本次流
```

**为什么必须先检测中断？** 因为中断时最后一条 messages 事件可能还来不及到达，先处理中断才能确保两端状态一致。

#### 二、完整请求链路（从用户输入到 SSE 返回）

##### 7 种 SSE 事件



```Plain Text
用户发送 "帮我新增采购订单"
  │
  ▼
POST /api/chat/stream {message: "帮我新增采购订单"}
  │
  ▼
chat_stream() → StreamingResponse
  │
  ▼
stream_chat_response(message="帮我新增采购订单")
  │ config = agent_loader.create_config(thread_id)
  │ current_input = {"messages": [{"role":"user", "content":"..."}]}
  │ display_messages = [user消息]
  │
  ▼
agent.astream(input, config, stream_mode=["messages","values"], subgraphs=True, version="v2")
  │
  ├─→ 主 Agent 收到消息 → 判断: 订单操作 → task(procurement-order)
  │
  ├─→ [SSE] token: "好的，我来帮您..."           (source: main)
  ├─→ [SSE] tool_start: task                    (source: main)
  ├─→ [SSE] tool_args: {...}                    (source: main)
  │
  ├─→ order 子 Agent 启动 (独立上下文)
  │     ├─→ 第1步: 提取数据
  │     ├─→ 第2步: Schema 校验 → partId 缺失!
  │     ├─→ 第3步: request_order_info(...)
  │     │     └─→ interrupt({"type": "order_info_request", ...})
  │     │
  ├─→ [stream_mode="values"] 检测到 interrupts
  │     │
  │     ├─→ [SSE] interrupt {interrupt_type: "order_info_supplement", ...}
  │     ├─→ save_display_messages(thread_id, cleaned)  ← 保存现场
  │     └─→ [SSE] done {interrupted: true}
  │         return  ← 流结束
  │
  ▼
前端 InterruptBanner 弹出: "请输入补充信息"
用户输入: "物料ID=100, 数量=50, 单价=25.5"
  │
  ▼
POST /api/chat/{thread_id}/resume {resume: {supplement: "物料ID=100..."}}
  │
  ▼
stream_chat_response(thread_id, resume_data={supplement: "..."})
  │ existing = get_display_messages()  ← 加载中断前的消息
  │ current_input = Command(resume={supplement: "..."})  ← 恢复
  │
  ▼
agent.astream(Command(resume=...), config, ...)
  │
  ├─→ order 子 Agent 恢复 → 解析补充数据 → 合并 → 校验通过
  ├─→ 构造 order_create 参数 → interrupt_on 触发
  │
  ├─→ [stream_mode="values"] 再次检测到 interrupts
  │     ├─→ [SSE] interrupt {interrupt_type: "hitl_approval", action_requests: [...]}
  │     └─→ [SSE] done {interrupted: true}
  │
  ▼
前端 InterruptBanner 切换: 审批卡片 (approve/reject)
用户点击 "approve"
  │
  ▼
POST /api/chat/{thread_id}/resume {resume: {decisions: [{type: "approve"}]}}
  │
  ▼
agent.astream(Command(resume={decisions:...}), config, ...)
  │
  ├─→ order_create 执行 → 成功
  ├─→ [SSE] tool_result {text: "订单创建成功..."}
  ├─→ [SSE] token "订单已创建，编号 PO20260513..."  (source: order)
  │
  ├─→ 主 Agent 收到子Agent 完成 → compact_conversation
  ├─→ [SSE] token "已为您完成订单创建..."           (source: main)
  │
  └─→ save_display_messages(thread_id, all_messages)
      [SSE] done {thread_id: "...", content: "..."}
```

