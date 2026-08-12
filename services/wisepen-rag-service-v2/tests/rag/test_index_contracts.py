import pytest

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.index.builders import (
    build_content_revision_id,
    build_reading_blocks,
    build_retrieval_chunks,
    build_source_refs,
    create_content_revision,
    parse_document_structure,
)
from rag.application.rag.index.builders.revisions import decide_stage
from rag.application.rag.read import (
    ContentNotFoundError,
    DocumentContentReader,
    DocumentStructureReader,
)
from rag.application.rag.verify import EvidenceVerifier
from rag.application.rag.verify import (
    EvidenceCorruptError,
    EvidenceNotFoundError,
    EvidenceRevisionError,
)
from rag.domain.models.acl import PermissionScope, ResourceAcl
from rag.domain.models.content import ResourceIndexState
from rag.domain.models.content import (
    ContentWindow,
    DocumentStructureResult,
    SectionContent,
    SectionFrontier,
)
from rag.domain.models.evidence import (
    EvidenceCandidate,
    EvidenceRecord,
)
from rag.domain.models.content import ReadingBlock
from rag.domain.repositories import StageAction
from rag.domain.models.retrieval import RetrievalChunk, SourceRef
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
    async def get_applied_document_structure(self, resource_id):
        return None

    async def get_applied_pages(self, resource_id, page_labels):
        return None

    async def get_applied_sections(self, resource_id, section_ids):
        return None


class _ReadableAclReader:
    async def get_resource_acls(self, resource_ids):
        return {
            resource_id: ResourceAcl(
                resource_id=resource_id,
                acl_revision=1,
                owner_id="user-1",
            )
            for resource_id in resource_ids
        }


class _DeniedAclReader:
    async def get_resource_acls(self, resource_ids):
        return {}


@pytest.mark.asyncio
async def test_read_actions_raise_directly_when_content_is_missing() -> None:
    reader = _MissingReader()
    authorizer = PermissionAuthorizer(reader=_ReadableAclReader())
    scope = PermissionScope(user_id="user-1")
    with pytest.raises(ContentNotFoundError):
        await DocumentStructureReader(reader=reader, authorizer=authorizer).get(
            resource_id="missing",
            permission_scope=scope,
        )
    with pytest.raises(ContentNotFoundError):
        await DocumentContentReader(reader=reader, authorizer=authorizer).get_pages(
            resource_id="missing",
            page_labels=["1"],
            permission_scope=scope,
        )
    with pytest.raises(ContentNotFoundError):
        await DocumentContentReader(reader=reader, authorizer=authorizer).get_sections(
            resource_id="missing",
            section_ids=["section"],
            permission_scope=scope,
        )


@pytest.mark.asyncio
async def test_read_actions_do_not_distinguish_denied_resource_from_missing() -> None:
    reader = _MissingReader()
    authorizer = PermissionAuthorizer(reader=_DeniedAclReader())
    scope = PermissionScope(user_id="user-1")

    with pytest.raises(ContentNotFoundError):
        await DocumentStructureReader(reader=reader, authorizer=authorizer).get(
            resource_id="private-resource",
            permission_scope=scope,
        )


def _evidence_facts() -> tuple[str, object, list[ReadingBlock], list[RetrievalChunk], list[SourceRef], object]:
    markdown = "# 标题\n\n正文内容。"
    revision_id = build_content_revision_id(
        resource_id="resource-1", document_version=1, markdown=markdown
    )
    structure = parse_document_structure(
        resource_id="resource-1",
        content_revision=revision_id,
        markdown=markdown,
    )
    blocks = build_reading_blocks(
        resource_id="resource-1",
        content_revision=revision_id,
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
    )
    chunks = build_retrieval_chunks(
        resource_id="resource-1",
        content_revision=revision_id,
        markdown=markdown,
        structure=structure,
        sections=structure.sections,
        reading_blocks=blocks,
    )
    refs = build_source_refs(
        resource_id="resource-1",
        content_revision=revision_id,
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
    return markdown, structure, blocks, chunks, refs, revision


class _EvidenceReader:
    def __init__(self, record: EvidenceRecord) -> None:
        self.record = record

    async def read_applied_evidence(self, resource_id, content_revision, source_ref_ids):
        if resource_id != self.record.revision.resource_id:
            return None
        if content_revision != self.record.revision.content_revision:
            raise EvidenceRevisionError(content_revision)
        return {self.record.source_ref.ref_id: self.record}


@pytest.mark.asyncio
async def test_verify_closes_index_to_authoritative_evidence() -> None:
    markdown, structure, blocks, chunks, refs, revision = _evidence_facts()
    record = EvidenceRecord(
        revision=revision,
        source_ref=refs[0],
        reading_block=blocks[0],
        section=next(section for section in structure.sections if section.section_id == refs[0].section_id),
        source_text=markdown[refs[0].source_spans[0].start_offset : refs[0].source_spans[0].end_offset],
    )
    verified = await EvidenceVerifier(reader=_EvidenceReader(record)).verify(
        [
            EvidenceCandidate(
                resource_id=revision.resource_id,
                content_revision=revision.content_revision,
                source_ref_id=refs[0].ref_id,
                chunk=chunks[0],
            )
        ],
    )
    assert verified == [record]


@pytest.mark.asyncio
async def test_verify_rejects_missing_ref_and_wrong_chunk_ownership() -> None:
    _, structure, blocks, chunks, refs, revision = _evidence_facts()
    record = EvidenceRecord(
        revision=revision,
        source_ref=refs[0],
        reading_block=blocks[0],
        section=next(section for section in structure.sections if section.section_id == refs[0].section_id),
        source_text=chunks[0].raw_text,
    )
    reader = _EvidenceReader(record)
    missing = EvidenceCandidate(
        resource_id=revision.resource_id,
        content_revision=revision.content_revision,
        source_ref_id="missing",
        chunk=chunks[0],
    )
    with pytest.raises(EvidenceNotFoundError):
        await EvidenceVerifier(reader=reader).verify([missing])

    wrong_chunk = RetrievalChunk(
        chunk_id="wrong",
        reading_block_id=chunks[0].reading_block_id,
        section_id=chunks[0].section_id,
        section_path=list(chunks[0].section_path),
        raw_text=chunks[0].raw_text,
        index_text=chunks[0].index_text,
        source_spans=list(chunks[0].source_spans),
        page_labels=list(chunks[0].page_labels),
        anchor_labels=list(chunks[0].anchor_labels),
    )
    with pytest.raises(EvidenceCorruptError):
        await EvidenceVerifier(reader=reader).verify(
            [
                EvidenceCandidate(
                    resource_id=revision.resource_id,
                    content_revision=revision.content_revision,
                    source_ref_id=refs[0].ref_id,
                    chunk=wrong_chunk,
                )
            ],
        )


@pytest.mark.asyncio
async def test_verify_refs_accepts_only_quote_from_authoritative_source() -> None:
    markdown, structure, blocks, _, refs, revision = _evidence_facts()
    record = EvidenceRecord(
        revision=revision,
        source_ref=refs[0],
        reading_block=blocks[0],
        section=next(
            section
            for section in structure.sections
            if section.section_id == refs[0].section_id
        ),
        source_text=markdown[
            refs[0].source_spans[0].start_offset : refs[0].source_spans[0].end_offset
        ],
    )
    verifier = EvidenceVerifier(reader=_EvidenceReader(record))

    verified = await verifier.verify_refs(
        resource_id=revision.resource_id,
        content_revision=revision.content_revision,
        source_ref_ids=[refs[0].ref_id],
        quotes=["正文内容"],
    )

    assert verified == [record]
    with pytest.raises(EvidenceCorruptError):
        await verifier.verify_refs(
            resource_id=revision.resource_id,
            content_revision=revision.content_revision,
            source_ref_ids=[refs[0].ref_id],
            quotes=["不存在的断言"],
        )
