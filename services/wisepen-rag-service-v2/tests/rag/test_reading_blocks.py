from itertools import pairwise

import pytest

from rag.application.rag.index import (
    build_flat_text_sections,
    build_reading_blocks,
    parse_document_structure,
)
from rag.domain.document_structure import StructureMode


def test_long_section_builds_multiple_ordered_reading_blocks() -> None:
    markdown = "# 长章节\n\n" + "段落内容🙂。" * 1800
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
    )
    blocks = build_reading_blocks(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
    )
    section = next(item for item in structure.sections if item.title == "长章节")
    section_blocks = [
        block for block in blocks if block.section_id == section.section_id
    ]

    assert len(section_blocks) > 1
    assert [block.ordinal for block in section_blocks] == list(
        range(len(section_blocks))
    )
    assert all(len(block.raw_text) <= 6000 for block in section_blocks)
    assert all(
        block.raw_text
        == "\n\n".join(
            markdown[span.start_offset : span.end_offset] for span in block.source_spans
        )
        for block in section_blocks
    )


def test_flat_text_builds_non_overlapping_sections_and_parent_blocks() -> None:
    markdown = "<!-- page 1 -->\n" + "无标题正文🙂。" * 2200
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
    )
    sections = build_flat_text_sections(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
    )
    blocks = build_reading_blocks(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
        structure=structure,
        sections=sections,
    )

    assert structure.mode is StructureMode.FLAT_TEXT
    assert len(sections) == len(blocks) > 1
    assert [section.title for section in sections] == [
        f"全文片段 {index}" for index in range(1, len(sections) + 1)
    ]
    assert all(block.ordinal == 0 for block in blocks)
    assert all(len(block.raw_text) <= 6000 for block in blocks)
    assert all("<!-- page" not in block.raw_text for block in blocks)
    assert all(
        left.source_spans[-1].end_offset <= right.source_spans[0].start_offset
        for left, right in pairwise(blocks)
    )


def test_reading_block_keeps_cross_page_and_anchor_attribution() -> None:
    markdown = (
        "<!-- page 1 -->\n\n# 数据\n\n"
        "Table 1: 样例\n\n| 名称 |\n|---|\n| 甲🙂 |\n\n"
        "<!-- page 2 -->\n\n补充正文。"
    )
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
    )
    blocks = build_reading_blocks(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
    )
    data_section = next(item for item in structure.sections if item.title == "数据")
    block = next(item for item in blocks if item.section_id == data_section.section_id)

    assert block.page_labels == ["1", "2"]
    assert block.anchor_labels == ["Table 1"]
    assert "甲🙂" in block.raw_text
    assert "<!-- page" not in block.raw_text


def test_heading_without_direct_body_has_no_reading_block() -> None:
    markdown = "# 父标题\n\n## 子标题\n\n子正文。"
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
    )
    blocks = build_reading_blocks(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
    )
    parent = next(item for item in structure.sections if item.title == "父标题")
    child = next(item for item in structure.sections if item.title == "子标题")

    assert [block for block in blocks if block.section_id == parent.section_id] == []
    assert len([block for block in blocks if block.section_id == child.section_id]) == 1


def test_empty_document_builds_no_reading_blocks() -> None:
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown="",
    )

    assert (
        build_reading_blocks(
            resource_id="resource-1",
            content_revision="revision-1",
            markdown="",
            structure=structure,
            sections=[],
        )
        == []
    )


def test_flat_text_rejects_sections_from_another_revision() -> None:
    markdown = "无标题正文。"
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision="revision-1",
        markdown=markdown,
    )
    sections = build_flat_text_sections(
        resource_id="resource-1",
        content_revision="revision-2",
        markdown=markdown,
    )

    with pytest.raises(ValueError, match="identity"):
        build_reading_blocks(
            resource_id="resource-1",
            content_revision="revision-1",
            markdown=markdown,
            structure=structure,
            sections=sections,
        )
