import pytest

from rag.application.rag.index import (
    build_content_revision_id,
    create_content_revision,
    parse_document_structure,
)
from rag.application.rag.index.revisions import decide_stage
from rag.application.rag.read import (
    ContentNotFoundError,
    read_document_structure,
    read_pages,
    read_sections,
)
from rag.domain.content_revision import ResourceIndexState
from rag.domain.repositories import StageAction
from rag.utils.chunkers import SourceSpan


def _revision(markdown: str = "# 标题\n\n正文🙂。"):
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
    return create_content_revision(
        resource_id="resource-1",
        document_version=1,
        markdown=markdown,
        structure=structure,
    )


def test_revision_identity_and_unicode_length_are_stable() -> None:
    revision = _revision()
    assert revision.content_revision == _revision().content_revision
    assert revision.total_length == len("# 标题\n\n正文🙂。")
    assert revision.content_hash


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
    ],
)
def test_stage_decision(state, expected) -> None:
    revision = _revision()
    if state is not None and state.applied_content_revision == "same":
        state.applied_content_revision = revision.content_revision
    assert decide_stage(revision, state) is expected


def test_same_document_version_with_corrected_content_is_staged() -> None:
    original = _revision("原文")
    corrected = _revision("修正后的原文")
    state = ResourceIndexState(
        resource_id="resource-1",
        applied_content_revision=original.content_revision,
        applied_document_version=1,
    )
    assert decide_stage(corrected, state) is StageAction.STAGED


def test_source_span_contract_uses_half_open_offsets() -> None:
    assert SourceSpan(1, 3).end_offset - SourceSpan(1, 3).start_offset == 2


class _MissingReader:
    async def read_applied_document_structure(self, resource_id):
        return None

    async def read_applied_pages(self, resource_id, page_labels):
        return None

    async def read_applied_sections(self, resource_id, section_ids):
        return None


@pytest.mark.asyncio
async def test_read_actions_raise_directly_when_content_is_missing() -> None:
    reader = _MissingReader()
    with pytest.raises(ContentNotFoundError):
        await read_document_structure(reader, resource_id="missing")
    with pytest.raises(ContentNotFoundError):
        await read_pages(reader, resource_id="missing", page_labels=["1"])
    with pytest.raises(ContentNotFoundError):
        await read_sections(reader, resource_id="missing", section_ids=["section"])
