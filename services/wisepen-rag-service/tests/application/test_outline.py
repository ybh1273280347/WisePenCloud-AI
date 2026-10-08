from types import SimpleNamespace

import pytest
from common.utils.markdown import MarkdownChunker

from rag.application.outline import OutlineBuilder
from rag.application.reading import DocumentReadError


class SnapshotStub:
    def __init__(self, document) -> None:
        self.document = document

    async def locate_sections(self, section_ids, *, scope):
        return {
            section.section_id: SimpleNamespace(document=self.document, section=section)
            for section in self.document.structure.sections
            if section.section_id in section_ids
        }

    async def load_documents(self, resource_ids, *, scope):
        return {self.document.resource_id: self.document}


@pytest.mark.asyncio
async def test_rag_outline_builder_uses_shared_global_and_neighborhood_format() -> None:
    source = (
        "# Parent\n\nParent text.\n\n"
        "## Before\n\nBefore text.\n\n"
        "## Current\n\nTable 1: Values\n\n| value |\n| --- |\n| 42 |\n\n"
        "### Child\n\nChild text.\n\n"
        "## After\n\nAfter text.\n"
    )
    result = MarkdownChunker().chunk(source)
    document = SimpleNamespace(
        resource_id="resource-1",
        structure=SimpleNamespace(
            sections=result.sections,
            anchors=result.anchors,
        ),
    )
    builder = OutlineBuilder(snapshots=SnapshotStub(document))
    current = next(section for section in result.sections if section.title == "Current")

    global_outline = await builder.global_outline(
        document.resource_id,
        max_level=1,
        scope=object(),
    )
    neighborhood = await builder.neighborhood(
        [current.section_id],
        sibling_steps=0,
        scope=object(),
    )

    assert "- Parent {" in global_outline
    assert "  - Current {" not in global_outline
    assert "[current]" in neighborhood[0].outline
    assert "[Table 1]" in neighborhood[0].outline
    assert "Child" in neighborhood[0].outline


@pytest.mark.asyncio
async def test_rag_outline_builder_keeps_invisible_section_behavior() -> None:
    document = SimpleNamespace(
        resource_id="resource-1",
        structure=SimpleNamespace(sections=[], anchors=[]),
    )
    builder = OutlineBuilder(snapshots=SnapshotStub(document))

    with pytest.raises(DocumentReadError, match="section is not visible"):
        await builder.neighborhood(["missing"], scope=object())
