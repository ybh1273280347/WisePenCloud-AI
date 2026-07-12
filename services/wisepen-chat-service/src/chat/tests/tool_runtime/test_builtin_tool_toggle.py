from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from chat.api.endpoints.tool import _initialize_builtin_tools, update_user_tool_config
from chat.api.schemas.tool import UpdateUserToolConfigRequest
from chat.application.tools.core import (
    ToolDefinition,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRegistry,
)


class _BuiltinTool:
    def __init__(self, name: str) -> None:
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name=name,
                description=name,
                parameters_schema=ToolParametersSchema({"type": "object", "properties": {}}),
            ),
            policy=ToolPolicy(expose_by_default=True, user_toggleable=True),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> None:
        return None


class _InMemoryToolConfigRepository:
    def __init__(self) -> None:
        self._configs: dict[str, SimpleNamespace] = {}

    async def get_tool_config(self, user_id: str, tool_name: str) -> SimpleNamespace | None:
        return self._configs.get(tool_name)

    async def list_tool_configs(self, user_id: str) -> list[SimpleNamespace]:
        return list(self._configs.values())

    async def upsert_tool_config(
        self,
        *,
        user_id: str,
        tool_name: str,
        enabled: bool,
        config: dict[str, Any],
        secret_config: dict[str, str],
        secret_fingerprints: dict[str, str],
        schema_version: int,
    ) -> SimpleNamespace:
        entity = SimpleNamespace(
            user_id=user_id,
            tool_name=tool_name,
            enabled=enabled,
            config=config,
            secret_config=secret_config,
            secret_fingerprints=secret_fingerprints,
            schema_version=schema_version,
        )
        self._configs[tool_name] = entity
        return entity


@pytest.mark.asyncio
async def test_init_builtin_tools_creates_default_enabled_config_once() -> None:
    repository = _InMemoryToolConfigRepository()
    registry = ToolRegistry(tool_config_repo=repository)
    registry.register(_BuiltinTool("web_fetch"))

    first = await _initialize_builtin_tools(
        user_id="user-1",
        tool_registry=registry,
        tool_config_repo=repository,
    )
    second = await _initialize_builtin_tools(
        user_id="user-1",
        tool_registry=registry,
        tool_config_repo=repository,
    )

    assert [tool.enabled for tool in first] == [True]
    assert [tool.enabled for tool in second] == [True]
    assert len(await repository.list_tool_configs("user-1")) == 1


@pytest.mark.asyncio
async def test_disabled_builtin_tool_is_not_exposed_by_registry() -> None:
    repository = _InMemoryToolConfigRepository()
    registry = ToolRegistry(tool_config_repo=repository)
    registry.register(_BuiltinTool("web_fetch"))
    await repository.upsert_tool_config(
        user_id="user-1",
        tool_name="web_fetch",
        enabled=False,
        config={},
        secret_config={},
        secret_fingerprints={},
        schema_version=1,
    )

    scope = await registry.derive(user_id="user-1")

    assert scope.get("web_fetch") is None


@pytest.mark.asyncio
async def test_update_user_tool_config_toggles_builtin_tool() -> None:
    repository = _InMemoryToolConfigRepository()
    registry = ToolRegistry(tool_config_repo=repository)
    registry.register(_BuiltinTool("web_fetch"))

    response = await update_user_tool_config(
        req=UpdateUserToolConfigRequest(tool_name="web_fetch", enabled=False),
        user_id="user-1",
        tool_registry=registry,
        tool_config_repo=repository,
    )

    assert response.data.enabled is False
