"""加载已审核的子 Agent 声明，并绑定其最小工具集。"""

from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar, overload

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_CONFIG_DIRECTORY = Path(__file__).with_name("configs")
_REQUIRED_CONFIG_NAMES = frozenset({"procurement-analyst", "procurement-order"})


class SubagentConfig(BaseModel):
    """单个 DeepAgents 子 Agent 的已审核声明式配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^procurement-(analyst|order)$")
    description: str = Field(min_length=1, max_length=500)
    tool_names: tuple[str, ...] = Field(min_length=1)
    model_call_limit: int = Field(default=50, ge=1, le=50)
    tool_call_limit: int = Field(default=200, ge=1, le=200)


ToolT = TypeVar("ToolT", str, BaseTool)


def load_subagent_configs(config_directory: Path | None = None) -> dict[str, SubagentConfig]:
    """加载仓库内已审核的两份 YAML 声明，不进行外部 I/O。"""

    directory = config_directory or _CONFIG_DIRECTORY
    configs: dict[str, SubagentConfig] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ValueError(f"invalid subagent configuration: {path.name}") from error
        if not isinstance(document, dict):
            raise ValueError(f"subagent configuration must be a mapping: {path.name}")
        try:
            config = SubagentConfig.model_validate(document)
        except ValidationError as error:
            raise ValueError(f"invalid subagent configuration: {path.name}") from error
        if config.name in configs:
            raise ValueError(f"duplicate subagent configuration: {config.name}")
        if len(set(config.tool_names)) != len(config.tool_names):
            raise ValueError(f"duplicate tool name in configuration: {config.name}")
        configs[config.name] = config
    if set(configs) != _REQUIRED_CONFIG_NAMES:
        raise ValueError("subagent configurations must define analyst and order agents")
    return configs


def _tool_name(tool: BaseTool | str) -> str:
    return tool if isinstance(tool, str) else tool.name


@overload
def resolve_subagent_tools(config: SubagentConfig, available_tools: Sequence[str]) -> list[str]: ...


@overload
def resolve_subagent_tools(config: SubagentConfig, available_tools: Sequence[BaseTool]) -> list[BaseTool]: ...


def resolve_subagent_tools(
    config: SubagentConfig, available_tools: Sequence[ToolT]
) -> list[ToolT]:
    """严格返回声明的工具，并保持 YAML 中的声明顺序。"""

    tools_by_name: dict[str, ToolT] = {}
    for tool in available_tools:
        name = _tool_name(tool)
        if name in tools_by_name:
            raise ValueError(f"duplicate available tool: {name}")
        tools_by_name[name] = tool
    missing = [name for name in config.tool_names if name not in tools_by_name]
    if missing:
        raise ValueError(f"{config.name} is missing approved tools: {', '.join(missing)}")
    return [tools_by_name[name] for name in config.tool_names]
