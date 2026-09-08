# ProcurePilot Agent

ProcurePilot Agent 是一个面向企业采购场景的 Python Agent 工程。项目以确定性的 Python 业务层为权威来源，通过 MCP 暴露受控能力，并使用 DeepAgents 编排分析与订单流程。

## 当前状态

当前只完成 M0 工程基线：Python 包、依赖锁、集中配置、测试与静态检查工具已经建立。采购领域模型、MySQL 持久化、MCP、Agent、OpenSandbox 和 FastAPI/SSE 尚未实现，也不会在导入模块时连接任何外部服务。

## 环境要求

- Windows 11 + PowerShell
- 固定解释器：`D:\py_venv\harness_agent\Scripts\python.exe`（Python 3.11.9）
- `uv`

本项目位于包含中文字符的路径中。Python 3.11 会使用系统编码读取 editable install 的 `.pth` 文件，可能导致 `src` 路径乱码，因此同步时固定使用 `--no-editable`。

## 安装

不要删除或重建现有虚拟环境。在项目根目录执行：

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'D:\py_venv\harness_agent'

uv lock --python 'D:\py_venv\harness_agent\Scripts\python.exe'
uv sync --python 'D:\py_venv\harness_agent\Scripts\python.exe' --no-editable
```

## 配置

复制安全模板后按本机环境填写，禁止提交真实密钥：

```powershell
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

`Settings` 可以在没有模型密钥时加载；只有代码显式调用 `require_model_config()` 初始化真实模型时，才要求设置 `MODEL_API_KEY`。测试环境的 `MYSQL_DSN` 数据库名必须包含 `test`，以防自动测试误连开发库或生产库。

## 验证

```powershell
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m ruff check src tests
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m mypy src
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m compileall -q src tests
```
