from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.core import (
    JsonSchemaCheck,
    ToolInvocation,
    ToolParametersSchema,
    ToolPolicy,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schema", "arguments", "message"),
    [
        (
            ToolParametersSchema(
                {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": False,
                },
            ),
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
                    },
                    "additionalProperties": False,
                },
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
