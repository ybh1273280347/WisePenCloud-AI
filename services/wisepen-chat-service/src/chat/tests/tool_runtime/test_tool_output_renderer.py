from __future__ import annotations

from chat.application.tools.tool_output_renderer import _render_regular_return, render_tool_xml


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
