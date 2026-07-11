from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from chat.application.tools.core.execution.result import ToolExecutionResult
from chat.application.tools.core.llm.invocation import ToolInvocation
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.tool_output_renderer import (
    ToolOutputRenderer,
    build_tool_result_payload,
    render_tool_output,
)


class _PayloadModel(BaseModel):
    name: str


def test_render_tool_output_uses_compact_json() -> None:
    rendered = render_tool_output({
        "status": "success",
        "data": {"items": [1, 2, 3]},
        "meta": {"cached": False},
    })

    assert rendered == (
        '{"status":"success","data":{"items":[1,2,3]},'
        '"meta":{"cached":false}}'
    )


def test_render_tool_output_adapts_common_tool_value_types() -> None:
    rendered = json.loads(render_tool_output({
        "model": _PayloadModel(name="test"),
        "decimal": Decimal("1.20"),
        "path": Path("report.pdf"),
        "binary": b"\xff\x00",
        "set": {"b", "a"},
        "datetime": datetime(2026, 7, 12, tzinfo=timezone.utc),
        "uuid": UUID("12345678-1234-5678-1234-567812345678"),
    }))

    assert rendered["model"] == {"name": "test"}
    assert rendered["decimal"] == "1.20"
    assert rendered["path"] == "report.pdf"
    assert rendered["binary"] == "\ufffd\u0000"
    assert set(rendered["set"]) == {"a", "b"}
    assert rendered["datetime"] == "2026-07-12T00:00:00+00:00"
    assert rendered["uuid"] == "12345678-1234-5678-1234-567812345678"


def test_render_tool_output_textualizes_unknown_type() -> None:
    rendered = json.loads(render_tool_output({"value": object()}))

    assert rendered["value"].startswith("<object object at 0x")


def test_build_tool_result_payload_keeps_contents_and_receipts() -> None:
    payload = build_tool_result_payload(
        {"status": "success"},
        inline_contents=("markdown",),
        content_receipts=({"content_id": "cnt_1"},),
    )

    assert payload == {
        "status": "success",
        "contents": ("markdown",),
        "content_receipts": ({"content_id": "cnt_1"},),
    }


def test_tool_return_tag_does_not_affect_json_rendering() -> None:
    now = datetime.now(timezone.utc)
    tool_result = ToolExecutionResult(
        tool_invocation=ToolInvocation(
            tool_call_id="call-1",
            tool_name="exa_search",
            tool_call_arguments={},
        ),
        tool_output=ToolReturn(
            tag="exa_search_result",
            visible_result={"query": "DeepSeek"},
        ),
        started_at=now,
        finished_at=now,
    )

    rendered = ToolOutputRenderer.render_result(tool_result=tool_result)

    assert json.loads(rendered.rendered_text) == {"query": "DeepSeek"}
