# M9 OpenSandbox 与 Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Agent 生成的代码、命令和分析产物限制在 OpenSandbox 中，并建立首个本地审核的采购分析 Skill。

**Architecture:** 项目先定义稳定的 Sandbox Adapter，普通测试使用 Fake Sandbox；真实适配器包装 OpenSandbox SDK，并实现 DeepAgents 需要的 SandboxBackendProtocol。Skills 由本地白名单同步，禁止运行时下载未知内容。

**Tech Stack:** OpenSandbox Python SDK、DeepAgents Backend Protocol、Docker Desktop、pytest

---

## 前置条件与安全边界

- M8 生命周期和存储边界通过。
- 真实集成测试前人工启动 Docker Desktop，并确认 Docker Engine 可用。
- 所有宿主机代码执行都属于失败；不能为了测试绕过 Sandbox。

### Task 1: 项目 Sandbox Protocol 和 Fake 实现

**Files:**
- Create: `src/agent/sandbox/__init__.py`
- Create: `src/agent/sandbox/protocol.py`
- Create: `src/agent/sandbox/fake.py`
- Test: `src/tests/unit/agent/sandbox/test_fake_sandbox.py`

协议至少支持 create/close、read/write、list/glob/grep、execute 和 artifact reference。所有路径使用 POSIX 沙箱绝对路径；timeout、输出上限和取消是必需参数。Fake 实现只模拟明确命令结果，不在宿主机执行用户代码。

### Task 2: 路径、URL 和输出安全

**Files:**
- Create: `src/agent/sandbox/security.py`
- Test: `src/tests/security/test_sandbox_boundaries.py`

实现路径规范化，拒绝 `..`、空字节、Windows 盘符、UNC、符号链接逃逸和允许根目录外访问。URL 策略只允许明确 https 域名，解析后拒绝内网、回环、链路本地、云元数据和 DNS 重绑定结果。输出按字节和 token 双重限长，超出后写沙箱文件并返回摘要引用。

### Task 3: OpenSandbox Adapter

**Files:**
- Create: `src/agent/sandbox/opensandbox_backend.py`
- Test: `src/tests/contract/agent/sandbox/test_backend_protocol.py`

使用项目锁定的 `opensandbox` SDK 版本。创建沙箱时固定镜像摘要或版本、非特权用户、CPU、内存、磁盘、进程和 TTL；默认无网络，不挂载宿主机敏感目录、Docker Socket、SSH 和生产凭据。

SDK 异常映射为 SandboxUnavailable、SandboxTimeout、SandboxPolicyDenied 和 SandboxExecutionError。close 必须幂等，并在异常路径销毁沙箱。

### Task 4: DeepAgents Backend 适配

**Files:**
- Create: `src/agent/sandbox/deepagents_backend.py`
- Test: `src/tests/contract/agent/sandbox/test_deepagents_backend.py`

逐项实现锁定版 `SandboxBackendProtocol`，不得凭当前主分支猜签名。文件读写、搜索和 execute 全部委托 OpenSandbox Adapter；不允许 fallback 到本地 subprocess 或宿主文件系统。

### Task 5: supplier-comparison Skill

**Files:**
- Create: `src/skills/procurement/supplier-comparison/SKILL.md`
- Create: `src/skills/procurement/supplier-comparison/scripts/build_report.py`
- Modify: `pyproject.toml`
- Test: `src/tests/contract/skills/test_supplier_comparison_skill.py`

`skills` 是 `src/` 下的资源目录，不放进 `procurepilot` Python 包；构建配置必须显式包含 SKILL 和脚本资源。

Skill 输入为已验证的结构化报价 JSON，输出 analysis JSON、CSV、PNG 和 Markdown 报告。脚本不得联网、不得读取凭据、不得修改业务数据。测试检查 frontmatter、输入 Schema、固定样例结果、报告引用和文件只写入允许目录。

远程 Skill 下载、自动安装、自我修改和自动持久化保持关闭。

### Task 6: 真实 OpenSandbox 验收

```powershell
docker version
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest src/tests/unit/agent/sandbox src/tests/contract/agent/sandbox src/tests/security/test_sandbox_boundaries.py -v
& 'D:\py_venv\harness_agent\Scripts\python.exe' -m pytest -m opensandbox_live -v
```

live 测试必须完成：创建沙箱、等待 ready、写读文件、执行受控 Python、生成报告、验证网络拒绝、关闭并确认销毁。Docker 未启动时标记“未运行”，不得声称 M9 全部验收完成。

同步 `rules/安全与红线.md`、`wiki/Agent运行机制.md` 和 `wiki/数据模型.md`。

**完成标准：** Agent 文件和执行能力仅存在于 Sandbox，安全攻击测试通过，真实沙箱生命周期有证据。

**建议提交：** `feat: isolate agent execution with opensandbox`

## 实施状态（2026-09-15）

- Task 1–5 已实现：稳定 Sandbox Protocol、不执行宿主命令的 Fake、路径/URL/输出安全策略、`opensandbox==0.1.16` 适配器、DeepAgents 0.4.12 Backend 和 `supplier-comparison` Skill。
- FastAPI 真实装配会为每个请求创建独立 Sandbox，同步本地审核白名单 Skill，并将同一 Backend 注入主 Agent 和两个子 Agent。
- 普通测试和安全攻击测试已纳入门禁。Task 6 真实 OpenSandbox 验收未运行，原因是当前 Docker Engine 不可用。
- SDK 层可明确传入 CPU、内存、TTL、无网络和无挂载策略；总磁盘与进程数仍需 OpenSandbox Server/容器部署策略的 live 证据。因此 M9 代码完成，但完成标准中的真实沙箱生命周期仍待验收。
