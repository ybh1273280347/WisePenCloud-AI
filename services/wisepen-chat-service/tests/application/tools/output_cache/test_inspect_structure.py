import json
from types import SimpleNamespace

import pytest
from common.utils.markdown import MarkdownChunker

from chat.application.tools.core.execution.executor import ToolExecutor
from chat.application.tools.session_tools.cached_tool_output_tools import (
    inspect_structure,
)


@pytest.mark.asyncio
async def test_inspect_structure_returns_common_markdown_outline(monkeypatch) -> None:
    result = MarkdownChunker().chunk(
        "# Heading\n\nBody text.\n\nTable 1: Values\n\n| value |\n| --- |\n| 42 |\n"
    )
    stored = SimpleNamespace(
        text="# Heading\n\nBody text.\n\n",
        sections=result.sections,
        anchors=result.anchors,
    )

    async def get_content(*, content_id: str, session_id: str):
        assert content_id == "content-1"
        assert session_id == "session-1"
        return stored

    monkeypatch.setattr(inspect_structure, "get_tool_content", get_content)
    tool = inspect_structure.CachedToolOutputInspectStructureTool()

    response = await tool.execute(
        {"session_id": "session-1"},
        content_id="content-1",
    )

    assert isinstance(response, inspect_structure.CachedToolOutputStructureResult)
    assert response.outline.startswith("- Heading {#")
    assert "[Table 1]" in response.outline
    assert response.total_length == len(stored.text)

    serialized = json.loads(ToolExecutor._coerce_tool_output(response).content)
    assert serialized["outline"] == response.outline
    assert serialized["total_length"] == len(stored.text)
