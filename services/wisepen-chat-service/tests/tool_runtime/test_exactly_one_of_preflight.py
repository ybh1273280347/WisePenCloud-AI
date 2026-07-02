from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.core import (
    ExactlyOneOfCheck,
    JsonSchemaCheck,
    ToolDefinition,
    ToolExactlyOneOf,
    ToolInvocation,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
)
from chat.application.tools.core.execution.executor import ToolExecutor
from chat.application.tools.core.llm.renderer import schema_renderer
from chat.application.tools.core.registry import ToolScope


class _SampleTool:
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="sample_tool",
                description="sample",
                parameters_schema=_schema(),
            )
        )

    async def execute(self, context: dict[str, object], **kwargs: object) -> dict[str, str]:
        return {"status": "called"}


def _schema() -> ToolParametersSchema:
    return ToolParametersSchema(
        {
            "type": "object",
            "properties": {
                "common": {"type": "string"},
                "range_start": {"type": "integer"},
                "range_end": {"type": "integer"},
                "selector": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        exactly_one_of=(
            ToolExactlyOneOf(
                groups=(("range_start", "range_end"), ("selector",)),
                message="Provide exactly one input group.",
            ),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {"range_start": 1, "range_end": 3},
        {"selector": "intro"},
        {"common": "allowed with selected group", "selector": "intro"},
    ],
)
async def test_exactly_one_of_accepts_one_complete_group(arguments: dict[str, object]) -> None:
    result = await ExactlyOneOfCheck().check(
        ToolInvocation(
            tool_call_id="call_1",
            tool_name="sample_tool",
            tool_call_arguments=arguments,
        ),
        ToolPolicy(),
        _schema(),
        {},
    )

    assert result.ok is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"range_start": 1},
        {"range_start": 1, "selector": "intro"},
        {"range_start": 1, "range_end": 3, "selector": "intro"},
    ],
)
async def test_exactly_one_of_rejects_missing_partial_or_multiple_groups(
    arguments: dict[str, object],
) -> None:
    result = await ExactlyOneOfCheck().check(
        ToolInvocation(
            tool_call_id="call_1",
            tool_name="sample_tool",
            tool_call_arguments=arguments,
        ),
        ToolPolicy(),
        _schema(),
        {},
    )

    assert result.ok is False
    assert result.message == "Provide exactly one input group."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schema", "arguments", "message"),
    [
        (
            _schema(),
            {"selector": "   "},
            "Invalid arguments for 'sample_tool' at selector: must not be blank.",
        ),
        (
            ToolParametersSchema(
                {
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                        },
                        "search_refs": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                        },
                    },
                    "additionalProperties": False,
                },
                exactly_one_of=(
                    ToolExactlyOneOf(groups=(("urls",), ("search_refs",))),
                ),
            ),
            {"urls": ["   "]},
            "Invalid arguments for 'sample_tool' at urls[0]: must not be blank.",
        ),
    ],
)
async def test_json_schema_rejects_blank_min_length_strings(
    schema: ToolParametersSchema,
    arguments: dict[str, object],
    message: str,
) -> None:
    result = await JsonSchemaCheck().check(
        ToolInvocation(
            tool_call_id="call_1",
            tool_name="sample_tool",
            tool_call_arguments=arguments,
        ),
        ToolPolicy(),
        schema,
        {},
    )

    assert result.ok is False
    assert result.message == message


def test_exactly_one_of_rejects_unknown_schema_fields() -> None:
    with pytest.raises(ValueError, match="references fields not defined"):
        ToolParametersSchema(
            {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "additionalProperties": False,
            },
            exactly_one_of=(
                ToolExactlyOneOf(groups=(("url",), ("search_ref",))),
            ),
        )


def test_exactly_one_of_is_not_rendered_to_llm_schema() -> None:
    rendered = schema_renderer(
        ToolLLMSpec(
            name="sample_tool",
            description="sample",
            parameters_schema=_schema(),
        )
    )

    assert "exactly_one_of" not in rendered["function"]["parameters"]
    assert rendered["function"]["parameters"]["properties"]["selector"]["type"] == "string"


@pytest.mark.asyncio
async def test_executor_runs_exactly_one_of_preflight() -> None:
    executor = ToolExecutor(
        ToolScope(tools={"sample_tool": _SampleTool()}, context={}),
        output_renderer=object(),
        output_cache=object(),
    )

    result = await executor._execute_raw(
        ToolInvocation(
            tool_call_id="call_1",
            tool_name="sample_tool",
            tool_call_arguments={
                "range_start": 1,
                "range_end": 3,
                "selector": "intro",
            },
        )
    )

    assert result.tool_execution_error is not None
    assert result.tool_execution_error.reason == "Tool Preflight Failed"
    assert result.tool_execution_error.detail_reason == "Provide exactly one input group."
