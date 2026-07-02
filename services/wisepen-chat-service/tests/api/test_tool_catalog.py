import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.tool_catalog import list_tool_catalog_items


def test_list_tool_catalog_items_returns_visible_tool_mappings() -> None:
    responses = list_tool_catalog_items()

    tool_names_by_key = {
        item.key: list(item.tool_names)
        for item in responses
    }

    assert list(tool_names_by_key) == ["web_search", "image_ocr", "math_tools"]
    assert tool_names_by_key["web_search"] == ["web_search", "academic_search"]
    assert tool_names_by_key["image_ocr"] == ["image_ocr"]
    assert tool_names_by_key["math_tools"] == [
        "calculus_solver",
        "linear_algebra_solver",
        "equation_solver",
        "stats_solver",
        "expression_solver",
    ]
