from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rag.application.rag.index import (
    build_content_revision_id,
    create_content_revision,
    parse_document_structure,
)
from rag.application.rag.index.resource_index_store import StageAction, decide_stage
from rag.core.persistence.mongo.resource_index_store import (
    MongoResourceIndexStore,
    split_source_parts,
)
from rag.domain.content_revision import ResourceIndexState
from rag.utils.chunkers import SourceSpan


def _revision(
    *,
    resource_id: str = "resource-1",
    document_version: int = 1,
    markdown: str = "# 标题\n\n正文🙂。",
):
    content_revision = build_content_revision_id(
        resource_id=resource_id,
        document_version=document_version,
        markdown=markdown,
    )
    structure = parse_document_structure(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
    )
    return create_content_revision(
        resource_id=resource_id,
        document_version=document_version,
        markdown=markdown,
        structure=structure,
    )


def _database() -> tuple[MagicMock, dict[str, MagicMock]]:
    collections = {
        name: MagicMock()
        for name in (
            "wisepen_rag_v2_resource_index_states",
            "wisepen_rag_v2_content_revisions",
            "wisepen_rag_v2_source_parts",
        )
    }
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


def test_content_revision_identity_precedes_structure_and_is_stable() -> None:
    markdown = "# 标题\n\n正文🙂。"
    content_revision = build_content_revision_id(
        resource_id="resource-1",
        document_version=1,
        markdown=markdown,
    )
    revision = _revision(markdown=markdown)

    assert revision.content_revision == content_revision
    assert revision.content_hash
    assert revision.total_length == len(markdown)
    assert revision.pages == []
    assert _revision(markdown=markdown).content_revision == content_revision
    assert _revision(markdown=markdown + "修订").content_revision != content_revision


def test_content_revision_embeds_page_ranges() -> None:
    markdown = "<!-- page 1 -->\n甲\n<!-- page 2 -->\n乙"
    revision = _revision(markdown=markdown)

    assert [page.page_label for page in revision.pages] == ["1", "2"]
    assert revision.pages[0].source_span.end_offset == markdown.index("<!-- page 2 -->")


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (None, StageAction.STAGED),
        (
            ResourceIndexState(
                resource_id="resource-1",
                applied_content_revision="same",
                applied_document_version=1,
            ),
            StageAction.ALREADY_APPLIED,
        ),
        (
            ResourceIndexState(
                resource_id="resource-1",
                applied_content_revision="newer",
                applied_document_version=2,
            ),
            StageAction.STALE,
        ),
        (
            ResourceIndexState(
                resource_id="resource-1",
                staged_content_revision="newer",
                staged_document_version=2,
            ),
            StageAction.STALE,
        ),
    ],
)
def test_stage_decision(
    state: ResourceIndexState | None,
    expected: StageAction,
) -> None:
    revision = _revision()
    if state is not None and state.applied_content_revision == "same":
        state.applied_content_revision = revision.content_revision

    assert decide_stage(revision, state) is expected


def test_same_document_version_with_corrected_content_is_staged() -> None:
    original = _revision(markdown="原文")
    corrected = _revision(markdown="修正后的原文")
    state = ResourceIndexState(
        resource_id="resource-1",
        applied_content_revision=original.content_revision,
        applied_document_version=1,
    )

    assert decide_stage(corrected, state) is StageAction.STAGED


@pytest.mark.asyncio
async def test_stage_writes_source_before_staged_pointer() -> None:
    database, collections = _database()
    store = MongoResourceIndexStore(database)
    revision = _revision()
    events: list[str] = []

    collections["wisepen_rag_v2_content_revisions"].replace_one.side_effect = (
        lambda *args, **kwargs: events.append("revision")
    )
    collections["wisepen_rag_v2_source_parts"].delete_many.side_effect = (
        lambda *args, **kwargs: events.append("delete_parts")
    )
    collections["wisepen_rag_v2_source_parts"].insert_many.side_effect = (
        lambda *args, **kwargs: events.append("insert_parts")
    )

    async def record_pointer(*args, **kwargs):
        events.append("staged_pointer")
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="new")

    collections[
        "wisepen_rag_v2_resource_index_states"
    ].update_one.side_effect = record_pointer

    action = await store.stage_revision(revision, "# 标题\n\n正文🙂。")

    assert action is StageAction.STAGED
    assert events == ["revision", "delete_parts", "insert_parts", "staged_pointer"]


@pytest.mark.asyncio
async def test_stage_rejects_revision_identity_that_does_not_match_source() -> None:
    database, collections = _database()
    store = MongoResourceIndexStore(database)
    revision = _revision(markdown="原文")

    with pytest.raises(ValueError, match="identity"):
        await store.stage_revision(revision, "修文")

    collections["wisepen_rag_v2_content_revisions"].replace_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_initialize_creates_v2_revision_and_source_indexes() -> None:
    database, collections = _database()
    store = MongoResourceIndexStore(database)

    await store.initialize()

    for collection in collections.values():
        collection.create_indexes.assert_awaited_once()
    state_indexes = collections[
        "wisepen_rag_v2_resource_index_states"
    ].create_indexes.await_args.args[0]
    revision_indexes = collections[
        "wisepen_rag_v2_content_revisions"
    ].create_indexes.await_args.args[0]
    source_indexes = collections[
        "wisepen_rag_v2_source_parts"
    ].create_indexes.await_args.args[0]
    assert state_indexes[0].document["unique"] is True
    assert revision_indexes[0].document["unique"] is True
    assert source_indexes[0].document["unique"] is True


@pytest.mark.asyncio
async def test_already_applied_revision_does_not_rewrite_source() -> None:
    database, collections = _database()
    revision = _revision()
    collections["wisepen_rag_v2_resource_index_states"].find_one.return_value = {
        "resource_id": revision.resource_id,
        "applied_content_revision": revision.content_revision,
        "applied_document_version": revision.document_version,
    }
    store = MongoResourceIndexStore(database)

    action = await store.stage_revision(revision, "# 标题\n\n正文🙂。")

    assert action is StageAction.ALREADY_APPLIED
    collections["wisepen_rag_v2_content_revisions"].replace_one.assert_not_awaited()
    collections["wisepen_rag_v2_source_parts"].insert_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_revision_does_not_rewrite_source() -> None:
    database, collections = _database()
    revision = _revision()
    collections["wisepen_rag_v2_resource_index_states"].find_one.return_value = {
        "resource_id": revision.resource_id,
        "applied_content_revision": "newer",
        "applied_document_version": revision.document_version + 1,
    }
    store = MongoResourceIndexStore(database)

    action = await store.stage_revision(revision, "# 标题\n\n正文🙂。")

    assert action is StageAction.STALE
    collections["wisepen_rag_v2_content_revisions"].replace_one.assert_not_awaited()
    collections["wisepen_rag_v2_source_parts"].insert_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_uses_exact_staged_revision_cas() -> None:
    database, collections = _database()
    store = MongoResourceIndexStore(database)
    revision = _revision()

    await store.apply_revision(revision)

    state_collection = collections["wisepen_rag_v2_resource_index_states"]
    state_filter = state_collection.update_one.await_args.args[0]
    assert state_filter == {
        "resource_id": revision.resource_id,
        "staged_content_revision": revision.content_revision,
        "staged_document_version": revision.document_version,
    }


@pytest.mark.asyncio
async def test_apply_rejects_revision_lost_to_concurrent_stage() -> None:
    database, collections = _database()
    revision = _revision()
    state_collection = collections["wisepen_rag_v2_resource_index_states"]
    state_collection.update_one.return_value = SimpleNamespace(
        matched_count=0,
        modified_count=0,
        upserted_id=None,
    )
    state_collection.find_one.return_value = {
        "resource_id": revision.resource_id,
        "staged_content_revision": "newer",
        "staged_document_version": 2,
    }
    store = MongoResourceIndexStore(database)

    with pytest.raises(RuntimeError, match="no longer staged"):
        await store.apply_revision(revision)


def test_large_unicode_source_is_split_without_coordinate_drift() -> None:
    markdown = "甲" * 999_999 + "🙂乙"
    revision = _revision(markdown=markdown)
    parts = split_source_parts(revision, markdown)

    assert len(parts) == 2
    assert parts[0].source_span == SourceSpan(0, 1_000_000)
    assert parts[1].source_span == SourceSpan(1_000_000, len(markdown))
    assert "".join(part.text for part in parts) == markdown


@pytest.mark.asyncio
async def test_read_source_text_across_parts() -> None:
    database, collections = _database()
    revision = _revision(markdown="甲乙丙丁")
    collections["wisepen_rag_v2_content_revisions"].find_one.return_value = {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "document_version": revision.document_version,
        "content_hash": revision.content_hash,
        "index_schema_version": revision.index_schema_version,
        "structure_mode": revision.structure_mode.value,
        "total_length": revision.total_length,
        "pages": [],
    }
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(
        return_value=[
            {
                "content_revision": revision.content_revision,
                "part_index": 0,
                "start_offset": 0,
                "end_offset": 2,
                "text": "甲乙",
            },
            {
                "content_revision": revision.content_revision,
                "part_index": 1,
                "start_offset": 2,
                "end_offset": 4,
                "text": "丙丁",
            },
        ]
    )
    collections["wisepen_rag_v2_source_parts"].find.return_value = cursor
    store = MongoResourceIndexStore(database)

    text = await store.read_source_text(
        revision.content_revision,
        [SourceSpan(1, 3)],
    )

    assert text == "乙丙"


@pytest.mark.asyncio
async def test_read_source_text_rejects_missing_part() -> None:
    database, collections = _database()
    revision = _revision(markdown="甲乙丙丁")
    collections["wisepen_rag_v2_content_revisions"].find_one.return_value = {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "document_version": revision.document_version,
        "content_hash": revision.content_hash,
        "index_schema_version": revision.index_schema_version,
        "structure_mode": revision.structure_mode.value,
        "total_length": revision.total_length,
        "pages": [],
    }
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    collections["wisepen_rag_v2_source_parts"].find.return_value = cursor
    store = MongoResourceIndexStore(database)

    with pytest.raises(RuntimeError, match="do not cover span"):
        await store.read_source_text(
            revision.content_revision,
            [SourceSpan(1, 3)],
        )
