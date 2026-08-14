from dataclasses import dataclass

import pytest

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.navigate import (
    EvidenceVerifier,
    LocateRequest,
    ReadingCandidateLocator,
    build_retrieved_section_views,
)
from rag.domain.models.acl import PermissionScope, ResourceAcl
from rag.domain.models.content import ContentRevision, ReadingBlock
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import KnowledgeNode, KnowledgeNodeKind
from rag.domain.models.navigation import NavigationState
from rag.domain.models.retrieval import RetrievalCandidate, SourceRef
from rag.domain.models.structure import Section, StructureMode
from rag.utils.chunkers import SourceSpan
from rag.utils.ranking import RankDecision, RankedCandidate, RankResult


@dataclass
class _EmbeddingResult:
    embeddings: list[list[float]]


class _EmbeddingClient:
    async def aembed(self, values):
        return _EmbeddingResult([[0.1, 0.2]])


class _CandidateSearch:
    def __init__(self, candidates):
        self.candidates = candidates

    async def search(self, request):
        return self.candidates


class _AclReader:
    async def get_resource_acls(self, resource_ids):
        return {
            resource_id: ResourceAcl(
                resource_id=resource_id,
                acl_revision=1,
                owner_id="user-1",
            )
            for resource_id in resource_ids
        }


class _RevisionReader:
    async def get_applied_revision(self, resource_id):
        return _revision(resource_id)


class _EvidenceReader:
    def __init__(self, records):
        self.records = records
        self.calls = []

    async def read_applied_evidence(self, resource_id, content_revision, source_ref_ids):
        self.calls.append(list(source_ref_ids))
        return {ref_id: self.records[ref_id] for ref_id in source_ref_ids}


class _RankingPipeline:
    def __init__(self, ranked_ids, decision=RankDecision.RELEVANT):
        self.ranked_ids = ranked_ids
        self.decision = decision

    async def arank(self, request):
        candidates = {item.candidate_id: item for item in request.candidates}
        return RankResult(
            ranked=tuple(
                RankedCandidate(
                    candidate=candidates[candidate_id],
                    rank=index,
                    score=1.0,
                )
                for index, candidate_id in enumerate(self.ranked_ids, 1)
            ),
            total_candidates=len(candidates),
            decision=self.decision,
        )


class _MentionLookup:
    async def find_nodes(self, **kwargs):
        return [
            KnowledgeNode(
                node_id="node-1",
                kind=KnowledgeNodeKind.ENTITY,
                label="主题",
                resource_id="internal-resource-field",
            )
        ]


class _StateStore:
    def __init__(self):
        self.created = None

    async def create(self, **kwargs):
        self.created = kwargs
        return NavigationState(state_id="nav-1", **kwargs)


def _revision(resource_id="resource-1") -> ContentRevision:
    return ContentRevision(
        resource_id=resource_id,
        content_revision="revision-1",
        document_version=1,
        content_hash="hash",
        index_schema_version="rag-v2-content:v2",
        structure_mode=StructureMode.SECTIONED,
        total_length=10,
    )


def _section() -> Section:
    return Section(
        section_id="section-1",
        title="当前标题",
        level=3,
        parent_section_id=None,
        ordinal=0,
        section_path=["很长的父标题", "当前标题"],
        own_span=SourceSpan(0, 10),
        subtree_span=SourceSpan(0, 10),
        content_spans=[SourceSpan(0, 10)],
    )


def _candidate(chunk_id, span, *, block_id="block-1") -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        reading_block_id=block_id,
        section_id="section-1",
        section_path=["很长的父标题", "当前标题"],
        resource_id="resource-1",
        content_revision="revision-1",
        raw_text="abcdefghij"[span.start_offset : span.end_offset],
        source_spans=[span],
        page_labels=["1"],
        anchor_labels=[],
        source_ref_id=f"ref-{chunk_id}",
        score=0.8,
    )


def _record(candidate) -> EvidenceRecord:
    return EvidenceRecord(
        revision=_revision(),
        source_ref=SourceRef(
            ref_id=candidate.source_ref_id,
            resource_id=candidate.resource_id,
            content_revision=candidate.content_revision,
            chunk_id=candidate.chunk_id,
            reading_block_id=candidate.reading_block_id,
            section_id=candidate.section_id,
            section_path=list(candidate.section_path),
            source_spans=list(candidate.source_spans),
            page_labels=list(candidate.page_labels),
            anchor_labels=[],
        ),
        reading_block=ReadingBlock(
            block_id=candidate.reading_block_id,
            section_id=candidate.section_id,
            ordinal=0,
            raw_text="abcdefghij",
            source_spans=[SourceSpan(0, 10)],
            page_labels=["1"],
        ),
        section=_section(),
        source_text=candidate.raw_text,
    )


def _candidate_id(candidate) -> str:
    return (
        f"{candidate.resource_id}\0{candidate.content_revision}\0{candidate.chunk_id}"
    )


def _locator(candidates, *, ranked_ids, decision=RankDecision.RELEVANT):
    records = {candidate.source_ref_id: _record(candidate) for candidate in candidates}
    state_store = _StateStore()
    evidence_reader = _EvidenceReader(records)
    locator = ReadingCandidateLocator(
        embedding_client=_EmbeddingClient(),
        candidate_search=_CandidateSearch(candidates),
        ranking_pipeline=_RankingPipeline(ranked_ids, decision),
        authorizer=PermissionAuthorizer(local_store=_AclReader()),
        evidence_verifier=EvidenceVerifier(reader=evidence_reader),
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader(),
        state_store=state_store,
    )
    return locator, state_store, evidence_reader


@pytest.mark.asyncio
async def test_locate_promotes_chunks_to_one_block_with_minimal_match_anchors() -> None:
    first = _candidate("chunk-1", SourceSpan(1, 4))
    second = _candidate("chunk-2", SourceSpan(6, 9))
    locator, state_store, _ = _locator(
        [first, second],
        ranked_ids=[_candidate_id(first), _candidate_id(second)],
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="问题",
            permission_scope=PermissionScope(user_id="user-1"),
            max_results=1,
        )
    )

    assert result.retrieval_status is RankDecision.RELEVANT
    assert result.sections[0].title == "当前标题"
    assert result.sections[0].section_path == "很长的父标题 > 当前标题"
    block = result.sections[0].reading_blocks[0]
    assert block.text == "abcdefghij"
    assert block.page_range == "1"
    assert not hasattr(block, "page_labels")
    assert [match.chunk_id for match in block.matches] == ["chunk-1", "chunk-2"]
    assert block.text[
        block.matches[0].ranges[0].start_offset : block.matches[0].ranges[0].end_offset
    ] == "bcd"
    assert not hasattr(block.matches[0], "text")
    assert not hasattr(result.sections[0], "level")
    assert not hasattr(result.nodes[0], "resource_id")
    assert state_store.created["known_node_ids"] == ["node-1"]
    assert "known_sections" not in state_store.created


def test_flat_text_retrieval_view_keeps_synthetic_section_context() -> None:
    candidate = _candidate("chunk-1", SourceSpan(0, 4))
    record = _record(candidate)
    record.revision.structure_mode = StructureMode.FLAT_TEXT
    record.section.title = "全文片段 1"
    record.section.section_path = ["全文片段 1"]

    section = build_retrieved_section_views([record])[0]

    assert section.title == "全文片段 1"
    assert section.section_path == "全文片段 1"
    assert section.reading_blocks[0].page_range == "1"


@pytest.mark.asyncio
async def test_locate_max_results_counts_blocks_not_chunks() -> None:
    first = _candidate("chunk-1", SourceSpan(0, 4), block_id="block-1")
    duplicate = _candidate("chunk-2", SourceSpan(4, 6), block_id="block-1")
    other = _candidate("chunk-3", SourceSpan(6, 10), block_id="block-2")
    locator, _, evidence_reader = _locator(
        [first, duplicate, other],
        ranked_ids=[
            _candidate_id(first),
            _candidate_id(duplicate),
            _candidate_id(other),
        ],
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="问题",
            permission_scope=PermissionScope(user_id="user-1"),
            max_results=1,
        )
    )

    assert [block.reading_block_id for block in result.sections[0].reading_blocks] == [
        "block-1"
    ]
    assert evidence_reader.calls == [["ref-chunk-1", "ref-chunk-2"]]


@pytest.mark.asyncio
async def test_locate_irrelevant_result_still_creates_graph_state() -> None:
    candidate = _candidate("chunk-1", SourceSpan(0, 4))
    locator, state_store, evidence_reader = _locator(
        [candidate],
        ranked_ids=[],
        decision=RankDecision.IRRELEVANT,
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="不相关",
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert result.retrieval_status is RankDecision.IRRELEVANT
    assert result.sections == []
    assert evidence_reader.calls == []
    assert state_store.created["known_node_ids"] == []
