from typing import Any

from chat.application.tools.core.definition import Tool
from chat.application.tools.core.llm.renderer import schema_renderer
from chat.domain.repositories import ToolConfigRepository


class ToolScope:
    """一次请求内的工具可见性和可信上下文快照"""

    def __init__(
            self,
            *,
            tools: dict[str, Tool],
            context: dict[str, Any] | None,
            configs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._tools = dict(tools)
        self._context = dict(context or {})
        self._configs = {
            name: dict(config)
            for name, config in (configs or {}).items()
            if name in self._tools
        }
        self._schemas = [
            schema_renderer(tool.definition.llm_spec)
            for tool in self._tools.values()
        ]

    def schemas(self) -> list[dict[str, Any]]:
        return list(self._schemas)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def config_for(self, name: str) -> dict[str, Any] | None:
        config = self._configs.get(name)
        return dict(config) if config is not None else None

    @property
    def context(self) -> dict[str, Any]:
        return dict(self._context)

    def __len__(self) -> int:
        return len(self._tools)


class ToolRegistry:
    """全局工具注册表，负责派生请求级工具视图"""

    def __init__(self, tool_config_repo: ToolConfigRepository) -> None:
        self._tool_config_repo = tool_config_repo
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.llm_spec.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        """返回全局已注册工具的 schema。

        该方法仅用于诊断和测试。运行期 LLM 调用必须使用 ToolScope.schemas()，
        确保已应用当前请求的 expose/allow/deny 过滤。
        """
        return [schema_renderer(tool.definition.llm_spec) for tool in self._tools.values()]

    async def derive(
            self,
            *,
            tool_context: dict[str, Any] | None = None,
            expose_tool_name_set: set[str] | None = None,
            allow_tool_name_set: set[str] | None = None,
            deny_tool_name_set: set[str] | None = None,
            user_id: str,
    ) -> ToolScope:
        context = dict(tool_context or {})
        expose_tool_name_set = expose_tool_name_set or set()
        deny_tool_name_set = deny_tool_name_set or set()

        tools: dict[str, Tool] = dict(self._tools)
        configured_tool_names, tool_configs, disabled_tool_names = await self._resolve_tool_configs(
            user_id=user_id,
            tools=tools,
        )

        filtered_tools: dict[str, Tool] = {}
        for name, tool in tools.items():
            policy = tool.definition.policy

            if name in disabled_tool_names:
                continue

            if tool.definition.config_spec is not None and name not in configured_tool_names:
                continue

            explicitly_exposed = name in expose_tool_name_set
            skill_exposed = bool(policy.required_allowed_builtin_skill_ids) and set(
                policy.required_allowed_builtin_skill_ids,
            ).issubset(set(context.get("allowed_skill_ids") or []))

            if not policy.expose_by_default:
                if explicitly_exposed or skill_exposed:
                    filtered_tools[name] = tool
                continue

            if allow_tool_name_set is not None and name not in allow_tool_name_set:
                continue
            if name in deny_tool_name_set:
                continue

            filtered_tools[name] = tool

        return ToolScope(
            tools=filtered_tools,
            context=context,
            configs=tool_configs,
        )

    def __len__(self) -> int:
        return len(self._tools)

    async def _resolve_tool_configs(
            self,
            *,
            user_id: str,
            tools: dict[str, Tool],
    ) -> tuple[set[str], dict[str, dict[str, Any]], set[str]]:
        # 获取需要配置，且已经配置好的 tool
        entities = {
            entity.tool_name: entity
            for entity in await self._tool_config_repo.list_tool_configs(user_id)
        }
        configured_tool_names: set[str] = set()
        tool_configs: dict[str, dict[str, Any]] = {}
        disabled_tool_names: set[str] = set()

        for name, tool in tools.items():
            config_spec = tool.definition.config_spec
            # 不需要配置的 tool
            if config_spec is None:
                entity = entities.get(name)
                if tool.definition.policy.user_toggleable and entity is not None and not entity.enabled:
                    disabled_tool_names.add(name)
                continue

            entity = entities.get(name)
            # 需要配置，但是数据库中不存在配置或未启用
            if entity is None or not entity.enabled:
                continue

            merged_config = {**entity.config, **entity.secret_config}
            if any(
                    (value := merged_config.get(key)) is None
                    or isinstance(value, str) and not value.strip()
                    for key in config_spec.required_keys
            ):
                continue

            configured_tool_names.add(name)
            tool_configs[name] = merged_config

        return configured_tool_names, tool_configs, disabled_tool_names
