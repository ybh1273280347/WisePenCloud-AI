from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rag.application.rag.index import (
    build_content_revision_id,
    build_reading_blocks,
    build_retrieval_chunks,
    build_source_refs,
    create_content_revision,
    parse_document_structure,
)
from rag.application.rag.index.resource_index_store import StageAction
from rag.core.persistence.mongo.resource_index_store import (
    MongoResourceIndexStore,
    _reading_block_document,
    _revision_document,
    _section_document,
    _source_part_document,
    _source_ref_document,
    split_source_parts,
)


def _indexed_document():
    markdown = "\n\n".join(
        [
            "<!-- page 1 -->",
            "# 数据",
            "Table 1: 样例\n\n| 值 |\n|---|\n| 甲🙂 |",
            "## 补充",
            "补充正文。",
        ]
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
    chunks = build_retrieval_chunks(
        resource_id="resource-1",
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
        reading_blocks=blocks,
    )
    refs = build_source_refs(
        resource_id="resource-1",
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
        reading_blocks=blocks,
        retrieval_chunks=chunks,
    )
    revision = create_content_revision(
        resource_id="resource-1",
        document_version=1,
        markdown=markdown,
        structure=structure,
    )
    return markdown, structure, blocks, refs, revision


def _database() -> tuple[MagicMock, dict[str, MagicMock]]:
    collection_names = (
        "wisepen_rag_v2_resource_index_states",
        "wisepen_rag_v2_content_revisions",
        "wisepen_rag_v2_source_parts",
        "wisepen_rag_v2_sections",
        "wisepen_rag_v2_reading_blocks",
        "wisepen_rag_v2_source_refs",
    )
    collections = {name: MagicMock() for name in collection_names}
    for collection in collections.values():
        collection.create_indexes = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        collection.replace_one = AsyncMock()
        collection.delete_many = AsyncMock()
        collection.insert_many = AsyncMock()
        collection.update_one = AsyncMock(
            return_value=SimpleNamespace(
                matched_count=1,
                modified_count=1,
                upserted_id=None,
            )
        )
    database = MagicMock()
    database.__getitem__.side_effect = collections.__getitem__
    return database, collections


@pytest.mark.asyncio
async def test_stage_writes_all_structure_before_staged_pointer() -> None:
    database, collections = _database()
    markdown, structure, blocks, refs, revision = _indexed_document()
    events: list[str] = []

    for name, event in (
        ("wisepen_rag_v2_content_revisions", "revision"),
        ("wisepen_rag_v2_source_parts", "source_parts"),
        ("wisepen_rag_v2_sections", "sections"),
        ("wisepen_rag_v2_reading_blocks", "reading_blocks"),
        ("wisepen_rag_v2_source_refs", "source_refs"),
    ):
        collections[name].insert_many.side_effect = (
            lambda *args, event=event, **kwargs: events.append(event)
        )
    collections["wisepen_rag_v2_content_revisions"].replace_one.side_effect = (
        lambda *args, **kwargs: events.append("revision")
    )

    async def record_pointer(*args, **kwargs):
        events.append("staged_pointer")
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="new")

    collections[
        "wisepen_rag_v2_resource_index_states"
    ].update_one.side_effect = record_pointer
    store = MongoResourceIndexStore(database)

    action = await store.stage_revision(
        revision,
        markdown,
        structure.sections,
        blocks,
        refs,
    )

    assert action is StageAction.STAGED
    assert events == [
        "revision",
        "source_parts",
        "sections",
        "reading_blocks",
        "source_refs",
        "staged_pointer",
    ]
    section_documents = collections[
        "wisepen_rag_v2_sections"
    ].insert_many.await_args.args[0]
    assert section_documents[1]["preview"]
    source_ref_documents = collections[
        "wisepen_rag_v2_source_refs"
    ].insert_many.await_args.args[0]
    assert source_ref_documents[0]["reading_block_id"] == refs[0].reading_block_id


@pytest.mark.asyncio
async def test_interrupted_structure_write_never_updates_staged_pointer() -> None:
    database, collections = _database()
    markdown, structure, blocks, refs, revision = _indexed_document()
    collections["wisepen_rag_v2_reading_blocks"].insert_many.side_effect = RuntimeError(
        "write failed"
    )
    store = MongoResourceIndexStore(database)

    with pytest.raises(RuntimeError, match="write failed"):
        await store.stage_revision(
            revision,
            markdown,
            structure.sections,
            blocks,
            refs,
        )

    collections["wisepen_rag_v2_resource_index_states"].update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_rejects_source_ref_with_wrong_reading_block() -> None:
    database, _ = _database()
    markdown, structure, blocks, refs, revision = _indexed_document()
    refs[0].reading_block_id = "missing-block"
    store = MongoResourceIndexStore(database)

    with pytest.raises(ValueError, match="invalid ownership"):
        await store.stage_revision(
            revision,
            markdown,
            structure.sections,
            blocks,
            refs,
        )


@pytest.mark.asyncio
async def test_delete_resources_removes_state_before_revision_data() -> None:
    database, collections = _database()
    events: list[str] = []
    revision_cursor = MagicMock()
    revision_cursor.to_list = AsyncMock(
        return_value=[{"content_revision": "revision-1"}]
    )
    collections["wisepen_rag_v2_content_revisions"].find.return_value = revision_cursor

    for name, event in (
        ("wisepen_rag_v2_resource_index_states", "state"),
        ("wisepen_rag_v2_source_parts", "source_parts"),
        ("wisepen_rag_v2_sections", "sections"),
        ("wisepen_rag_v2_reading_blocks", "reading_blocks"),
        ("wisepen_rag_v2_source_refs", "source_refs"),
        ("wisepen_rag_v2_content_revisions", "revisions"),
    ):
        collections[name].delete_many.side_effect = (
            lambda *args, event=event, **kwargs: events.append(event)
        )
    store = MongoResourceIndexStore(database)

    await store.delete_resources(["resource-1", "resource-1"])

    assert events == [
        "state",
        "source_parts",
        "sections",
        "reading_blocks",
        "source_refs",
        "revisions",
    ]


@pytest.mark.asyncio
async def test_graph_build_source_requires_requested_applied_revision() -> None:
    database, collections = _database()
    _, _, _, _, revision = _indexed_document()
    collections["wisepen_rag_v2_resource_index_states"].find_one.return_value = {
        "resource_id": revision.resource_id,
        "applied_content_revision": "different-revision",
        "applied_document_version": 2,
    }
    store = MongoResourceIndexStore(database)

    with pytest.raises(RuntimeError, match="is not applied"):
        await store.read_graph_build_source(
            revision.resource_id,
            revision.content_revision,
        )


@pytest.mark.asyncio
async def test_graph_build_source_restores_applied_structure_and_evidence() -> None:
    database, collections = _database()
    markdown, structure, blocks, refs, revision = _indexed_document()
    collections["wisepen_rag_v2_resource_index_states"].find_one.return_value = {
        "resource_id": revision.resource_id,
        "applied_content_revision": revision.content_revision,
        "applied_document_version": revision.document_version,
    }
    collections[
        "wisepen_rag_v2_content_revisions"
    ].find_one.return_value = _revision_document(revision)

    def cursor(documents):
        value = MagicMock()
        value.sort.return_value = value
        value.to_list = AsyncMock(return_value=documents)
        return value

    collections["wisepen_rag_v2_source_parts"].find.return_value = cursor(
        [_source_part_document(part) for part in split_source_parts(revision, markdown)]
    )
    collections["wisepen_rag_v2_sections"].find.return_value = cursor(
        [_section_document(revision, section) for section in structure.sections]
    )
    collections["wisepen_rag_v2_reading_blocks"].find.return_value = cursor(
        [_reading_block_document(revision, block) for block in blocks]
    )
    collections["wisepen_rag_v2_source_refs"].find.return_value = cursor(
        [_source_ref_document(revision, source_ref) for source_ref in refs]
    )
    store = MongoResourceIndexStore(database)

    source = await store.read_graph_build_source(
        revision.resource_id,
        revision.content_revision,
    )

    assert source.markdown == markdown
    assert source.sections == structure.sections
    assert source.reading_blocks == blocks
    assert source.source_refs == refs


@pytest.mark.asyncio
async def test_initialize_creates_structure_and_source_ref_indexes() -> None:
    database, collections = _database()
    store = MongoResourceIndexStore(database)

    await store.initialize()

    section_indexes = collections[
        "wisepen_rag_v2_sections"
    ].create_indexes.await_args.args[0]
    block_indexes = collections[
        "wisepen_rag_v2_reading_blocks"
    ].create_indexes.await_args.args[0]
    ref_indexes = collections[
        "wisepen_rag_v2_source_refs"
    ].create_indexes.await_args.args[0]
    assert section_indexes[0].document["unique"] is True
    assert block_indexes[0].document["unique"] is True
    assert ref_indexes[0].document["unique"] is True
    assert ref_indexes[1].document["unique"] is True
