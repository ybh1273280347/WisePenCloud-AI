from __future__ import annotations

import json
from datetime import datetime, timezone

from chat.application.tools.core.execution.result import ToolExecutionResult
from chat.application.tools.core.llm.invocation import ToolInvocation
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools import tool_output_renderer as renderer_module
from chat.application.tools.tool_output_renderer import (
    ToolOutputRenderer,
    _render_regular_return,
    render_tool_xml,
)


def test_render_tool_xml_filters_none_fields_and_items() -> None:
    rendered = render_tool_xml(
        root_tag="result",
        payload={
            "title": "example",
            "empty_field": None,
            "nested": {
                "keep": "value",
                "drop": None,
            },
            "items": [
                "first",
                None,
                {"name": "kept", "unused": None},
            ],
        },
    )

    assert "<empty_field>" not in rendered
    assert "<drop>" not in rendered
    assert rendered.count("<item>") == 2
    assert "<title>example</title>" in rendered
    assert "<name>kept</name>" in rendered


def test_regular_return_none_keeps_empty_root() -> None:
    visible_result, rendered = _render_regular_return(root_tag="result", value=None)

    assert visible_result == {}
    assert rendered == "<result/>\n"


def test_render_tool_xml_removes_xml_invalid_control_characters() -> None:
    rendered = render_tool_xml(
        root_tag="result",
        payload={"text": "before\x00after\x0btext"},
    )

    assert "\x00" not in rendered
    assert "\x0b" not in rendered
    assert "beforeaftertext" in rendered


def test_render_tool_xml_falls_back_to_raw_json_when_xml_rendering_fails(
        monkeypatch,
) -> None:
    def raise_render_error(*args, **kwargs):
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(
        renderer_module,
        "_mapping_element",
        raise_render_error,
    )

    rendered = render_tool_xml(
        root_tag="result",
        payload={"query": "DeepSeek\x00latest"},
        inline_contents=("detail",),
    )

    assert json.loads(rendered) == {
        "result": {"query": "DeepSeek\x00latest"},
        "contents": ["detail"],
    }


def test_render_result_falls_back_when_tool_return_tag_is_invalid() -> None:
    now = datetime.now(timezone.utc)
    tool_result = ToolExecutionResult(
        tool_invocation=ToolInvocation(
            tool_call_id="call-1",
            tool_name="exa_search",
            tool_call_arguments={},
        ),
        tool_output=ToolReturn(
            tag="invalid tag",
            visible_result={"query": "DeepSeek"},
        ),
        started_at=now,
        finished_at=now,
    )

    rendered = ToolOutputRenderer.render_result(tool_result=tool_result)

    assert json.loads(rendered.rendered_text) == {
        "result": {"query": "DeepSeek"},
    }
