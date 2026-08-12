from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.application.rag.index import (
    build_content_revision_id,
    build_reading_blocks,
    create_content_revision,
    parse_document_structure,
)
from rag.application.rag.read import (
    ContentNotFoundError,
    read_document_structure,
    read_pages,
    read_sections,
)
from rag.core.persistence.mongo.content_reader import MongoContentReader
from rag.core.persistence.mongo.content_records import (
    reading_block_document,
    revision_document,
    section_document,
    source_part_document,
)
from rag.core.persistence.mongo.resource_index_store import split_source_parts


def _cursor(documents: list[dict[str, object]]) -> MagicMock:
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=documents)
    return cursor


def _facts():
    markdown = (
        "<!-- page 1 -->\n\n# Alpha\n\nalpha body\n\n## Beta\n\n"
        "beta body\n\n## Gamma\n\ngamma body\n\n<!-- page 2 -->\n\n"
        "## Delta\n\ndelta body"
    )
    content_revision = build_content_revision_id(
        resource_id="resource-1",
        document_version=1,
        markdown=markdown,
    )
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision=content_revision,
        markdown=markdown,
    )
    blocks = build_reading_blocks(
        resource_id="resource-1",
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
    )
    revision = create_content_revision(
        resource_id="resource-1",
        document_version=1,
        markdown=markdown,
        structure=structure,
    )
    return markdown, structure, blocks, revision


def _database(markdown, structure, blocks, revision):
    names = (
        "wisepen_rag_v2_resource_index_states",
        "wisepen_rag_v2_content_revisions",
        "wisepen_rag_v2_source_parts",
        "wisepen_rag_v2_sections",
        "wisepen_rag_v2_reading_blocks",
    )
    collections = {name: MagicMock() for name in names}
    database = MagicMock()
    database.__getitem__.side_effect = collections.__getitem__
    state = {"resource_id": "resource-1", "applied_content_revision": revision.content_revision}
    collections[names[0]].find_one = AsyncMock(return_value=state)
    collections[names[1]].find_one = AsyncMock(return_value=revision_document(revision))
    collections[names[2]].find.return_value = _cursor(
        [source_part_document(part) for part in split_source_parts(revision, markdown)]
    )
    section_documents = [section_document(revision, section) for section in structure.sections]
    block_documents = [reading_block_document(revision, block) for block in blocks]
    collections[names[3]].find.return_value = _cursor(section_documents)
    collections[names[4]].find.return_value = _cursor(block_documents)
    return database


@pytest.mark.asyncio
async def test_read_actions_use_applied_revision_and_return_navigation() -> None:
    markdown, structure, blocks, revision = _facts()
    reader = MongoContentReader(_database(markdown, structure, blocks, revision))

    result = await read_document_structure(reader, resource_id="resource-1")
    assert [section.title for section in result.sections] == [
        "",
        "Alpha",
        "Beta",
        "Gamma",
        "Delta",
    ]

    pages = await read_pages(reader, resource_id="resource-1", page_labels=["1"])
    assert pages["1"].text == markdown[: revision.pages[0].source_span.end_offset]
    assert pages["1"].anchor_labels == []

    sections = await read_sections(
        reader,
        resource_id="resource-1",
        section_ids=[structure.sections[2].section_id],
    )
    beta = sections[structure.sections[2].section_id]
    assert [block.raw_text for block in beta.reading_blocks] == ["beta body\n"]
    assert beta.frontier.previous is None
    assert beta.frontier.next is not None
    assert beta.frontier.next.title == "Gamma"
    assert beta.frontier.parent is not None
    assert beta.frontier.parent.title == "Alpha"


@pytest.mark.asyncio
async def test_read_actions_raise_when_no_applied_revision_exists() -> None:
    database = MagicMock()
    database.__getitem__.side_effect = lambda _: MagicMock(
        find_one=AsyncMock(return_value=None)
    )
    reader = MongoContentReader(database)

    with pytest.raises(ContentNotFoundError):
        await read_document_structure(reader, resource_id="missing")
    with pytest.raises(ContentNotFoundError):
        await read_pages(reader, resource_id="missing", page_labels=["1"])
    with pytest.raises(ContentNotFoundError):
        await read_sections(reader, resource_id="missing", section_ids=["section"])


@pytest.mark.asyncio
async def test_missing_requested_page_or_section_is_an_empty_result() -> None:
    markdown, structure, blocks, revision = _facts()
    reader = MongoContentReader(_database(markdown, structure, blocks, revision))

    assert await read_pages(reader, resource_id="resource-1", page_labels=["9"]) == {}
    assert await read_sections(reader, resource_id="resource-1", section_ids=["missing"]) == {}
