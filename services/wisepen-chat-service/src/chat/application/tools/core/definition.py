from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, Dict, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from chat.application.tools.core.execution.hooks.base import ToolPreflightHook

ToolOutput = Any


class ToolTimeoutStrategy(StrEnum):
    CANCEL_TASK = "cancel_task"
    MARK_TIMEOUT_ONLY = "mark_timeout_only"


class ToolRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ToolExactlyOneOf:
    groups: tuple[tuple[str, ...], ...]
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.groups, tuple):
            raise TypeError("exactly_one_of groups must be a tuple.")
        if len(self.groups) < 2:
            raise ValueError("exactly_one_of must contain at least two groups.")

        for group in self.groups:
            if not isinstance(group, tuple):
                raise TypeError("exactly_one_of groups must contain tuples.")
            if not group:
                raise ValueError("exactly_one_of groups must not be empty.")
            if not all(isinstance(field_name, str) and field_name for field_name in group):
                raise ValueError("exactly_one_of groups must contain non-empty field names.")
            if len(set(group)) != len(group):
                raise ValueError("exactly_one_of groups must not contain duplicate fields.")


@dataclass(frozen=True)
class ToolParametersSchema:
    raw: dict[str, Any]
    exactly_one_of: tuple[ToolExactlyOneOf, ...] = ()

    def __post_init__(self) -> None:
        self._validate_schema(self.raw)
        self._validate_exactly_one_of()

    @property
    def properties(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("properties") or {}

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(self.raw.get("required") or ())

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)

    @staticmethod
    def _validate_schema(schema: dict[str, Any]) -> None:
        if not isinstance(schema, dict):
            raise TypeError("parameters_schema must be a dict.")

        if schema.get("type") != "object":
            raise ValueError("parameters_schema.type must be 'object'.")

        ToolParametersSchema._validate_schema_node(schema, path="parameters_schema")

    @staticmethod
    def _validate_schema_node(schema: dict[str, Any], *, path: str) -> None:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"{path}.properties must be a dict.")

        required = schema.get("required", [])
        if not isinstance(required, (list, tuple)):
            raise ValueError(f"{path}.required must be a list or tuple.")

        if not all(isinstance(item, str) for item in required):
            raise ValueError(f"{path}.required must contain only strings.")

        unknown_required = [
            item for item in required
            if item not in properties
        ]

        if unknown_required:
            raise ValueError(
                f"{path}.required contains keys not defined in properties: {unknown_required}"
            )

        items = schema.get("items")
        if items is not None and not isinstance(items, dict):
            raise ValueError(f"{path}.items must be a dict.")

        for key, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                raise ValueError(f"{path}.properties.{key} must be a dict.")
            ToolParametersSchema._validate_schema_node(
                property_schema,
                path=f"{path}.properties.{key}",
            )

        if isinstance(items, dict):
            ToolParametersSchema._validate_schema_node(items, path=f"{path}.items")

    def _validate_exactly_one_of(self) -> None:
        properties = self.properties
        for rule in self.exactly_one_of:
            if not isinstance(rule, ToolExactlyOneOf):
                raise TypeError("exactly_one_of must contain ToolExactlyOneOf instances.")

            seen_fields: set[str] = set()
            for group in rule.groups:
                duplicate_fields = [
                    field_name for field_name in group
                    if field_name in seen_fields
                ]
                if duplicate_fields:
                    raise ValueError(
                        "exactly_one_of groups must not share fields: "
                        f"{duplicate_fields}"
                    )
                seen_fields.update(group)

                unknown_fields = [
                    field_name for field_name in group
                    if field_name not in properties
                ]
                if unknown_fields:
                    raise ValueError(
                        "exactly_one_of references fields not defined in properties: "
                        f"{unknown_fields}"
                    )


@dataclass(frozen=True)
class ToolLLMSpec:
    name: str
    description: str
    parameters_schema: ToolParametersSchema

@dataclass(frozen=True)
class ToolPolicy:
    """工具策略"""
    expose_by_default: bool = False # 是否默认暴露给模型

    timeout_seconds: float | None = None # 超时时间
    timeout_strategy: ToolTimeoutStrategy = ToolTimeoutStrategy.CANCEL_TASK # 超时后策略

    persist_output: bool = False # 是否持久化输出 (如果不持久化则需要生成占位符)
    persisted_output_placeholder_factory: Callable[[dict, Any], str | None] = lambda tool_call_arguments, output: None # 持久化输出的占位生成器
    cache_chunked: bool = True # cacheable_texts 入库时是否生成 chunks/index

    risk_level: ToolRiskLevel = ToolRiskLevel.LOW # 风险级别

    required_context_keys: tuple[str, ...] = () # 需要的上下文Key

    max_output_chars: int | None = None # 输出最大字符数（超过后截断）
    allow_parallel: bool = False # 允许并行


@dataclass(frozen=True)
class ToolDefinition:
    llm_spec: ToolLLMSpec
    policy: ToolPolicy = field(default_factory=ToolPolicy)
    preflight_hooks: tuple['ToolPreflightHook', ...] = ()


class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition:
        ...

    async def execute(self, context: Dict[str, Any], **kwargs) -> ToolOutput:
        ...
