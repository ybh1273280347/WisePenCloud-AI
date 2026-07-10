from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, ValidationError, validators

from chat.application.tools.core.definition import ToolParametersSchema, ToolPolicy
from chat.application.tools.core.execution.hooks.base import (
    ToolPreflightHook,
    ToolPreflightResult,
)
from chat.application.tools.core.llm.invocation import ToolInvocation

_DEFAULT_MIN_LENGTH_VALIDATOR = Draft202012Validator.VALIDATORS["minLength"]


def _validate_min_length(
        validator,
        min_length: int,
        value: Any,
        schema: dict[str, Any],
):
    """扩展 minLength：声明非空字符串时，同时拒绝纯空白内容。"""
    if (
            isinstance(min_length, int)
            and min_length >= 1
            and isinstance(value, str)
            and value
            and not value.strip()
    ):
        yield ValidationError("must not be blank")
        return

    yield from _DEFAULT_MIN_LENGTH_VALIDATOR(
        validator,
        min_length,
        value,
        schema,
    )


_ToolParametersValidator = validators.extend(
    Draft202012Validator,
    {"minLength": _validate_min_length},
)


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
        missing = [
            key
            for key in policy.required_context_keys
            if key not in context
        ]
        if missing:
            return ToolPreflightResult(
                ok=False,
                message=(
                    f"Missing required context keys for tool "
                    f"'{invocation.tool_name}': {missing}"
                ),
            )

        return ToolPreflightResult(ok=True)


class JsonSchemaCheck(ToolPreflightHook):
    """校验工具调用参数是否符合 JSON Schema。"""

    name = "json_schema"

    async def check(
            self,
            invocation: ToolInvocation,
            policy: ToolPolicy,
            parameters_schema: ToolParametersSchema,
            context: dict[str, Any],
    ) -> ToolPreflightResult:
        validator = _ToolParametersValidator(parameters_schema.raw)
        error = next(
            iter(validator.iter_errors(invocation.tool_call_arguments)),
            None,
        )

        if error is None:
            return ToolPreflightResult(ok=True)

        path = "arguments" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.absolute_path
        )
        return ToolPreflightResult(
            ok=False,
            message=(
                f"Invalid arguments for '{invocation.tool_name}' "
                f"at {path}: {error.message}"
            ),
        )