from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from chat.application.tools.core import (
    ToolConfigSpec,
    ToolDefinition,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRegistry,
)


class _FakeTool:
    def __init__(self, name: str, *, requires_api_key: bool) -> None:
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name=name,
                description=name,
                parameters_schema=ToolParametersSchema({"type": "object", "properties": {}}),
            ),
            policy=ToolPolicy(expose_by_default=True),
            config_spec=(
                ToolConfigSpec(
                    schema={
                        "type": "object",
                        "properties": {"api_key": {"type": "string"}},
                    },
                    required_keys=("api_key",),
                    secret_keys=("api_key",),
                )
                if requires_api_key
                else None
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
            self,
            context: dict[str, Any],
            config: dict[str, Any] | None = None,
            **kwargs: Any,
    ) -> None:
        return None


class _FakeToolConfigRepository:
    def __init__(self, configs: list[object]) -> None:
        self._configs = configs

    async def list_tool_configs(self, user_id: str) -> list[object]:
        return self._configs


@pytest.mark.asyncio
async def test_configured_search_tool_is_exposed_with_secret_config() -> None:
    registry = ToolRegistry(
        tool_config_repo=_FakeToolConfigRepository([
            SimpleNamespace(
                tool_name="exa_search",
                enabled=True,
                config={},
                secret_config={"api_key": "user-key"},
            ),
        ]),
    )
    registry.register(_FakeTool("platform_search", requires_api_key=False))
    registry.register(_FakeTool("exa_search", requires_api_key=True))

    scope = await registry.derive(user_id="user-1")

    assert scope.get("platform_search") is not None
    assert scope.get("exa_search") is not None
    assert scope.config_for("exa_search") == {"api_key": "user-key"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        None,
        SimpleNamespace(
            tool_name="exa_search",
            enabled=False,
            config={},
            secret_config={"api_key": "user-key"},
        ),
        SimpleNamespace(
            tool_name="exa_search",
            enabled=True,
            config={},
            secret_config={"api_key": "   "},
        ),
    ],
)
async def test_unconfigured_search_tool_is_hidden(config: object | None) -> None:
    repository = _FakeToolConfigRepository([] if config is None else [config])
    registry = ToolRegistry(tool_config_repo=repository)
    registry.register(_FakeTool("platform_search", requires_api_key=False))
    registry.register(_FakeTool("exa_search", requires_api_key=True))

    scope = await registry.derive(user_id="user-1")

    assert scope.get("platform_search") is not None
    assert scope.get("exa_search") is None
