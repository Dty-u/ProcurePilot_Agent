# ProcurePilot Agent

ProcurePilot Agent 是一个面向企业采购场景的 Python Agent 工程。项目以确定性的 Python 业务层为权威来源，通过 MCP 暴露受控能力，并使用 DeepAgents 编排分析与订单流程。

## 当前状态

当前已完成 M0–M10 的源码和非 live 自动验收：在 M0–M8 的领域层、MCP、DeepAgents、HITL 和 MySQL 状态基础上，M9 增加 OpenSandbox 适配、DeepAgents Sandbox Backend 和本地审核的供应商比价 Skill；M10 增加 FastAPI、SSE、HTTP 恢复和展示历史接口。

Agent 状态仍全部使用 MySQL，不使用 SQLite。API 为每个可信请求绑定 MCP 身份和独立 Sandbox，Agent 的文件、命令和 Skill 脚本不回退到宿主机执行。当前 Docker Engine 未可用，因此 OpenSandbox 真实容器生命周期验收仍为“未运行”；生产认证适配器也未提供，`APP_ENV=production` 会失败关闭。模块导入不会连接模型、数据库、MCP 或 Sandbox。

## 环境要求

- Windows 11 + PowerShell
- 固定解释器：`D:\py_venv\harness_agent\Scripts\python.exe`（Python 3.11.9）
- `uv`
- Docker Desktop 与可用的 OpenSandbox Server（只在真实 Sandbox 运行时需要）

本项目位于包含中文字符的路径中。Python 3.11 会使用系统编码读取 editable install 的 `.pth` 文件，可能导致 `src` 路径乱码，因此同步时固定使用 `--no-editable`。

## 安装

不要删除或重建现有虚拟环境。在项目根目录执行：

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'D:\py_venv\harness_agent'

uv lock --python 'D:\py_venv\harness_agent\Scripts\python.exe'
uv sync --python 'D:\py_venv\harness_agent\Scripts\python.exe' --no-editable `
    --reinstall-package procurepilot-agent
```

`--reinstall-package procurepilot-agent` 用于确保修改源码后重新构建本地非 editable wheel，避免固定环境继续使用旧的项目安装包。

## 配置

复制安全模板后按本机环境填写，禁止提交真实密钥：

```powershell
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

`Settings` 可以在没有模型密钥和 Checkpoint DSN 时加载；只有代码显式初始化对应资源时才要求配置。测试环境的 `MYSQL_DSN` 和 `AGENT_CHECKPOINT_MYSQL_DSN` 数据库名都必须包含 `test`，以防自动测试误连开发库或生产库。

`AGENT_CHECKPOINT_MYSQL_DSN` 必须指向与 `MYSQL_DSN` 不同的 MySQL 数据库；允许共用 MySQL 服务，但不能共用数据库。该 Agent 数据库使用不同表分别保存 Checkpoint、Store、安全恢复元数据和脱敏展示消息。Checkpoint/Store 表由社区实现（非 LangGraph 官方包）`langgraph-checkpoint-mysql==3.0.0` 管理，恢复和展示表由 M8 生命周期显式初始化；这些表均不进入业务 Alembic 迁移。

首次创建或明确升级 Agent 状态表时，临时设置 `AGENT_CHECKPOINT_AUTO_SETUP=true` 后启动应用；确认成功后恢复为 `false`。该操作会在独立 Agent 数据库中初始化 Checkpoint、Store、Resume 和展示历史表，不能指向业务库、开发业务库或生产业务库。

`OPENSANDBOX_IMAGE` 必须是经审核的非 root 镜像，并以 `@sha256:<64位摘要>` 锁定。未配置时 API 可导入，但在创建真实 Agent 请求时会安全失败。

## FastAPI 与 SSE

开发/测试环境使用受控 Header 适配器：`X-User-ID`、`X-User-Name` 和 `X-Roles`。这些 Header 只用于本地验收，不是生产认证方案。

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m uvicorn `
    api_view.app:create_app --factory --host 127.0.0.1 --port 18000
```

已实现 `POST /api/chat/stream`、`POST /api/chat/{thread_id}/resume`、`GET /api/history`、`GET /api/history/{thread_id}` 和 `DELETE /api/history/{thread_id}`。SSE 仅输出 `token`、`tool_start`、`tool_args`、`tool_result`、`tool_end`、`interrupt`、`done` 七类事件。

MySQL 初始迁移只在已核对 `.env` 中的开发库连接后手动执行：

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m alembic upgrade head
```

## 命令行 Agent Demo

确认 `.env` 已配置可用的 `MODEL_*`、`MYSQL_DSN` 和独立的 `AGENT_CHECKPOINT_MYSQL_DSN`，且数据库中已有对应的物料、供应商、报价及订单操作数据。在项目根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path

& 'D:\py_venv\harness_agent\Scripts\python.exe' -m agent.cli_demo `
    '比较物料 part-001、采购数量 100 件的有效报价并给出建议'
```

Demo 会在进程内创建真实 MCP Server 和 MCP Client，打开 MySQL Checkpoint 与 MySQL Store 生命周期，登记线程归属，随后创建两套 MCP Agent 工具并组装主 Agent，最后输出主 Agent 的回复。它使用代码固定的本地演示身份，只用于本机验证，不应作为生产入口。需要 Sandbox/Skill 和 SSE 时请使用 FastAPI 入口。

## 验证

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src
git diff --check
```

`opensandbox_live` 需要人工确认 Docker/OpenSandbox 可用后再设置 `RUN_OPENSANDBOX_TESTS=1`；MySQL 集成测试只允许 `APP_ENV=test` 且库名包含 `test` 的专用库。
