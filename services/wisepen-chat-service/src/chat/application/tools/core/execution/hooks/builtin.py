from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from chat.application.tools.core.definition import ToolExactlyOneOf, ToolParametersSchema, ToolPolicy
from chat.application.tools.core.execution.hooks.base import ToolPreflightHook, ToolPreflightResult
from chat.application.tools.core.llm.invocation import ToolInvocation


class RequiredContextCheck(ToolPreflightHook):
    """校验工具执行所需的 context key 是否齐备。"""

    name = "required_context"

    async def check(
            self,
            invocation: ToolInvocation,
            policy: ToolPolicy,
            parameters_schema: ToolParametersSchema,
            context: dict[str, Any],
    ) -> ToolPreflightResult:
        if missing := [key for key in policy.required_context_keys if key not in context]:
            return ToolPreflightResult(
                ok=False,
                message=f"Missing required context keys for tool '{invocation.tool_name}': {missing}",
            )
        return ToolPreflightResult(ok=True)


class JsonSchemaCheck(ToolPreflightHook):
    """校验工具调用参数是否符合 JSON Schema。

    委托给 jsonschema 库，而非手写递归校验器。
    OpenAI function-calling 协议禁用 oneOf/anyOf/allOf/$ref，schema 永远是单一线性路径，
    所以不需要 best_match 那套多分支裁决逻辑——iter_errors 的第一条就是唯一会出现的错误。
    对 `minLength: 1` 字符串补充 trim 后空白检查，弥补 jsonschema 不拒绝 `"   "` 的行为。
    """

    name = "json_schema"

    async def check(
            self,
            invocation: ToolInvocation,
            policy: ToolPolicy,
            parameters_schema: ToolParametersSchema,
            context: dict[str, Any],
    ) -> ToolPreflightResult:
        validator = Draft202012Validator(parameters_schema.raw)

        error = next(iter(validator.iter_errors(invocation.tool_call_arguments)), None)
        if error is None:
            blank_path = _blank_min_length_string_path_at(
                parameters_schema.raw,
                invocation.tool_call_arguments,
                path=(),
            )

            if blank_path is None:
                return ToolPreflightResult(ok=True)
            return ToolPreflightResult(
                ok=False,
                message=(
                    f"Invalid arguments for '{invocation.tool_name}' at {blank_path}: "
                    "must not be blank."
                ),
            )

        return ToolPreflightResult(ok=False, message=_format_error(error, invocation.tool_name))


class ExactlyOneOfCheck(ToolPreflightHook):
    """校验内部参数组 one-of 约束。

    这类规则不能放进 OpenAI 可见 JSON Schema，但适合在 schema preflight 后统一执行。
    """

    name = "exactly_one_of"

    async def check(
            self,
            invocation: ToolInvocation,
            policy: ToolPolicy,
            parameters_schema: ToolParametersSchema,
            context: dict[str, Any],
    ) -> ToolPreflightResult:
        for rule in parameters_schema.exactly_one_of:
            matched_group = _matched_exactly_one_group(rule, invocation.tool_call_arguments)
            if matched_group is None:
                return ToolPreflightResult(
                    ok=False,
                    message=rule.message or _format_exactly_one_of_error(rule, invocation.tool_name),
                )

        return ToolPreflightResult(ok=True)


def _format_error(error: ValidationError, tool_name: str) -> str:
    """将 jsonschema 的 ValidationError 转为人类可读提示，仅拼接路径前缀。"""
    # absolute_path 是 deque，形如 deque(['a', 'b', 0])；点号拼接成 JSON Pointer 风格路径
    path = ".".join(str(part) for part in error.absolute_path) or "arguments"
    return f"Invalid arguments for '{tool_name}' at {path}: {error.message}"


def _matched_exactly_one_group(
        rule: ToolExactlyOneOf,
        arguments: dict[str, Any],
) -> tuple[str, ...] | None:
    argument_keys = set(arguments)
    matched_group: tuple[str, ...] | None = None

    for group in rule.groups:
        group_keys = set(group)
        # 参数组必须完整出现；只出现组内一部分字段时属于半组命中，直接判失败。
        if group_keys <= argument_keys:
            if matched_group is not None:
                return None
            matched_group = group
            continue
        if group_keys & argument_keys:
            return None

    return matched_group


def _format_exactly_one_of_error(rule: ToolExactlyOneOf, tool_name: str) -> str:
    groups = [
        " + ".join(group)
        for group in rule.groups
    ]
    return f"Invalid arguments for '{tool_name}': provide exactly one of {', '.join(groups)}."


def _blank_min_length_string_path_at(
        schema: dict[str, Any],
        value: Any,
        *,
        path: tuple[str, ...] = (),
) -> str | None:
    schema_type = schema.get("type")

    if schema_type == "string":
        min_length = schema.get("minLength")
        # jsonschema 的 minLength 按原始长度计算，"   " 仍会通过，这里补上工具参数语义里的非空白约束。
        if (
                isinstance(min_length, int)
                and min_length >= 1
                and isinstance(value, str)
                and not value.strip()
        ):
            return _format_schema_path(path)
        return None

    if schema_type == "object" and isinstance(value, dict):
        properties = schema.get("properties") or {}
        if not isinstance(properties, dict):
            return None
        for field_name, property_schema in properties.items():
            if field_name not in value or not isinstance(property_schema, dict):
                continue
            blank_path = _blank_min_length_string_path_at(
                property_schema,
                value[field_name],
                path=(*path, field_name),
            )
            if blank_path is not None:
                return blank_path
        return None

    if schema_type == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if not isinstance(item_schema, dict):
            return None
        for index, item in enumerate(value):
            blank_path = _blank_min_length_string_path_at(
                item_schema,
                item,
                path=(*path, f"[{index}]"),
            )
            if blank_path is not None:
                return blank_path
        return None

    return None


def _format_schema_path(path: tuple[str, ...]) -> str:
    if not path:
        return "arguments"

    formatted = ""
    for part in path:
        if part.startswith("["):
            formatted += part
            continue
        if formatted:
            formatted += "."
        formatted += part
    return formatted
