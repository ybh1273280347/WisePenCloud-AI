from dataclasses import dataclass

import pytest

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.locate import LocateError, LocateRequest, ReadingEntryLocator
from rag.application.rag.verify import EvidenceVerifier
from rag.domain.acl import PermissionScope, ResourceAcl
from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section, StructureMode
from rag.domain.evidence import EvidenceRecord
from rag.domain.knowledge_graph import KnowledgeNode, KnowledgeNodeKind
from rag.domain.navigation import NavigationState
from rag.domain.read_content import DocumentStructureResult
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import RetrievalCandidate, SourceRef
from rag.utils.chunkers import SourceSpan
from rag.utils.ranking import (
    RankDecision,
    RankedCandidate,
    RankResult,
)


@dataclass
class _EmbeddingClient:
    calls: list[list[str]]

    async def aembed(self, input):
        self.calls.append(list(input))
        return _EmbeddingResult(embeddings=[[0.1, 0.2, 0.3]])


@dataclass
class _EmbeddingResult:
    embeddings: list[list[float]]


class _CandidateSearch:
    def __init__(self, candidates):
        self.candidates = candidates
        self.request = None

    async def search(self, request):
        self.request = request
        return self.candidates


class _AclReader:
    def __init__(self, resource_ids):
        self.resource_ids = resource_ids

    async def get_resource_acls(self, resource_ids):
        return {
            resource_id: ResourceAcl(
                resource_id=resource_id,
                acl_revision=1,
                owner_id="owner",
                readable_users=["user-1"],
            )
            for resource_id in resource_ids
            if resource_id in self.resource_ids
        }


class _RevisionReader:
    def __init__(self, revisions):
        self.revisions = revisions

    async def get_applied_revision(self, resource_id):
        return self.revisions.get(resource_id)


class _EvidenceReader:
    def __init__(self, records):
        self.records = records
        self.calls = []

    async def read_applied_evidence(self, resource_id, content_revision, source_ref_ids):
        self.calls.append((resource_id, content_revision, list(source_ref_ids)))
        records = {
            ref_id: self.records[ref_id]
            for ref_id in source_ref_ids
            if ref_id in self.records
        }
        return records or None


class _StructureReader:
    def __init__(self, structure):
        self.structures = (
            structure
            if isinstance(structure, dict)
            else {structure.revision.resource_id: structure}
        )

    async def get_applied_document_structure(self, resource_id):
        return self.structures.get(resource_id)


class _StateStore:
    def __init__(self):
        self.created = []

    async def create(self, **kwargs):
        state = NavigationState(state_id="nav-1", **kwargs)
        self.created.append(state)
        return state


class _MentionLookup:
    def __init__(self, nodes=None):
        self.nodes = nodes or []

    async def find_nodes(self, **kwargs):
        return self.nodes


class _RankingPipeline:
    def __init__(self, ranked, decision=RankDecision.RELEVANT):
        self.ranked = ranked
        self.decision = decision
        self.request = None

    async def arank(self, request):
        self.request = request
        candidates = {candidate.candidate_id: candidate for candidate in request.candidates}
        return RankResult(
            ranked=tuple(
                RankedCandidate(
                    candidate=candidates[candidate_id],
                    rank=index,
                    score=0.9,
                )
                for index, candidate_id in enumerate(self.ranked, 1)
            ),
            total_candidates=len(request.candidates),
            decision=self.decision,
            decision_score=0.9,
        )


def _revision() -> ContentRevision:
    return ContentRevision(
        resource_id="resource-1",
        content_revision="revision-1",
        document_version=1,
        content_hash="hash",
        index_schema_version="v1",
        structure_mode=StructureMode.SECTIONED,
        total_length=20,
    )


def _section(section_id, *, parent_section_id=None, ordinal=0) -> Section:
    return Section(
        section_id=section_id,
        title=section_id,
        level=1,
        parent_section_id=parent_section_id,
        ordinal=ordinal,
        section_path=[section_id],
        own_span=SourceSpan(0, 20),
        subtree_span=SourceSpan(0, 20),
    )


def _candidate(chunk_id, *, block_id, section_id="section-1", revision="revision-1"):
    return RetrievalCandidate(
        chunk_id=chunk_id,
        reading_block_id=block_id,
        section_id=section_id,
        section_path=[section_id],
        resource_id="resource-1",
        content_revision=revision,
        raw_text=f"正文 {chunk_id}",
        source_spans=[SourceSpan(0, 8)],
        page_labels=["1"],
        anchor_labels=[],
        source_ref_id=f"ref-{chunk_id}",
        score=0.8,
    )


def _record(candidate, section, revision) -> EvidenceRecord:
    source_ref = SourceRef(
        ref_id=candidate.source_ref_id,
        resource_id=candidate.resource_id,
        content_revision=candidate.content_revision,
        chunk_id=candidate.chunk_id,
        reading_block_id=candidate.reading_block_id,
        section_id=candidate.section_id,
        section_path=list(candidate.section_path),
        source_spans=list(candidate.source_spans),
        page_labels=list(candidate.page_labels),
        anchor_labels=list(candidate.anchor_labels),
    )
    return EvidenceRecord(
        revision=revision,
        source_ref=source_ref,
        reading_block=ReadingBlock(
            block_id=candidate.reading_block_id,
            section_id=candidate.section_id,
            ordinal=0,
            raw_text=candidate.raw_text,
            source_spans=list(candidate.source_spans),
            page_labels=list(candidate.page_labels),
        ),
        section=section,
        source_text=candidate.raw_text,
    )


def _candidate_id(candidate: RetrievalCandidate) -> str:
    return (
        f"{candidate.resource_id}\0{candidate.content_revision}\0{candidate.chunk_id}"
    )


@pytest.mark.asyncio
async def test_locate_embeds_once_reranks_and_keeps_multiple_blocks_in_one_section():
    revision = _revision()
    root = _section("root")
    section = _section("section-1", parent_section_id="root")
    sibling = _section("section-2", parent_section_id="root", ordinal=1)
    candidates = [
        _candidate("chunk-1", block_id="block-1"),
        _candidate("chunk-2", block_id="block-1"),
        _candidate("chunk-3", block_id="block-2"),
    ]
    records = {_candidate.source_ref_id: _record(_candidate, section, revision) for _candidate in candidates}
    embedding = _EmbeddingClient(calls=[])
    search = _CandidateSearch(candidates)
    ranking = _RankingPipeline([_candidate_id(candidate) for candidate in candidates])
    state_store = _StateStore()
    locator = ReadingEntryLocator(
        embedding_client=embedding,
        candidate_search=search,
        ranking_pipeline=ranking,
        authorizer=PermissionAuthorizer(reader=_AclReader({"resource-1"})),
        evidence_verifier=EvidenceVerifier(reader=_EvidenceReader(records)),
        mention_lookup=_MentionLookup(
            [
                KnowledgeNode(
                    node_id="node-1",
                    kind=KnowledgeNodeKind.ENTITY,
                    label="Alpha",
                )
            ]
        ),
        revision_reader=_RevisionReader({"resource-1": revision}),
        structure_reader=_StructureReader(
            DocumentStructureResult(revision=revision, sections=[root, section, sibling])
        ),
        state_store=state_store,
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="完整问题",
            permission_scope=PermissionScope(user_id="user-1"),
            max_results=3,
        )
    )

    assert embedding.calls == [["完整问题"]]
    assert search.request.lexical_query == "完整问题"
    assert [signal.rank for signal in ranking.request.signals] == [1, 2, 3]
    assert result.decision is RankDecision.RELEVANT
    assert [node.node_id for node in result.nodes] == ["node-1"]
    assert len(result.sections) == 1
    assert [item.reading_block_id for item in result.sections[0].evidence] == [
        "block-1",
        "block-2",
    ]
    assert result.sections[0].frontier.next == sibling
    assert set(state_store.created[0].known_sections) == {"root", "section-1", "section-2"}
    assert state_store.created[0].known_node_ids == ["node-1"]


@pytest.mark.asyncio
async def test_locate_filters_acl_and_old_revisions_before_reranking():
    revision = _revision()
    section = _section("section-1")
    stale = _candidate("stale", block_id="stale", revision="revision-old")
    denied = _candidate("denied", block_id="denied")
    denied.resource_id = "resource-denied"
    valid = _candidate("valid", block_id="valid")
    records = {valid.source_ref_id: _record(valid, section, revision)}
    ranking = _RankingPipeline([_candidate_id(valid)])
    locator = ReadingEntryLocator(
        embedding_client=_EmbeddingClient(calls=[]),
        candidate_search=_CandidateSearch([stale, denied, valid]),
        ranking_pipeline=ranking,
        authorizer=PermissionAuthorizer(reader=_AclReader({"resource-1"})),
        evidence_verifier=EvidenceVerifier(reader=_EvidenceReader(records)),
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader({"resource-1": revision}),
        structure_reader=_StructureReader(
            DocumentStructureResult(revision=revision, sections=[section])
        ),
        state_store=_StateStore(),
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="问题",
            lexical_query="术语",
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert ranking.request.query.text == "问题"
    assert [candidate.candidate_id for candidate in ranking.request.candidates] == [
        _candidate_id(valid)
    ]
    assert result.sections[0].evidence[0].source_ref_id == "ref-valid"


@pytest.mark.asyncio
async def test_locate_keeps_same_chunk_id_from_different_resources_distinct():
    first_revision = _revision()
    second_revision = _revision()
    second_revision.resource_id = "resource-2"
    first_section = _section("section-1")
    second_section = _section("section-2")
    first = _candidate("shared", block_id="block-1", section_id="section-1")
    second = _candidate("shared", block_id="block-2", section_id="section-2")
    second.resource_id = "resource-2"
    second.source_ref_id = "ref-resource-2-shared"
    records = {
        first.source_ref_id: _record(first, first_section, first_revision),
        second.source_ref_id: _record(second, second_section, second_revision),
    }
    candidate_ids = [_candidate_id(candidate) for candidate in (first, second)]
    locator = ReadingEntryLocator(
        embedding_client=_EmbeddingClient(calls=[]),
        candidate_search=_CandidateSearch([first, second]),
        ranking_pipeline=_RankingPipeline(candidate_ids),
        authorizer=PermissionAuthorizer(
            reader=_AclReader({"resource-1", "resource-2"})
        ),
        evidence_verifier=EvidenceVerifier(reader=_EvidenceReader(records)),
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader(
            {"resource-1": first_revision, "resource-2": second_revision}
        ),
        structure_reader=_StructureReader(
            {
                "resource-1": DocumentStructureResult(
                    revision=first_revision,
                    sections=[first_section],
                ),
                "resource-2": DocumentStructureResult(
                    revision=second_revision,
                    sections=[second_section],
                ),
            }
        ),
        state_store=_StateStore(),
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="问题",
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert [section.resource_id for section in result.sections] == [
        "resource-1",
        "resource-2",
    ]


@pytest.mark.asyncio
async def test_locate_irrelevant_decision_creates_empty_state_without_verification():
    revision = _revision()
    candidate = _candidate("chunk-1", block_id="block-1")
    evidence_reader = _EvidenceReader({})
    state_store = _StateStore()
    locator = ReadingEntryLocator(
        embedding_client=_EmbeddingClient(calls=[]),
        candidate_search=_CandidateSearch([candidate]),
        ranking_pipeline=_RankingPipeline([], decision=RankDecision.IRRELEVANT),
        authorizer=PermissionAuthorizer(reader=_AclReader({"resource-1"})),
        evidence_verifier=EvidenceVerifier(reader=evidence_reader),
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader({"resource-1": revision}),
        structure_reader=_StructureReader(
            DocumentStructureResult(revision=revision, sections=[])
        ),
        state_store=state_store,
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="不相关问题",
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert result.decision is RankDecision.IRRELEVANT
    assert result.sections == []
    assert evidence_reader.calls == []
    assert state_store.created[0].known_sections == {}


@pytest.mark.asyncio
async def test_locate_uncertain_decision_keeps_verified_entry():
    revision = _revision()
    section = _section("section-1")
    candidate = _candidate("chunk-1", block_id="block-1")
    locator = ReadingEntryLocator(
        embedding_client=_EmbeddingClient(calls=[]),
        candidate_search=_CandidateSearch([candidate]),
        ranking_pipeline=_RankingPipeline(
            [_candidate_id(candidate)],
            decision=RankDecision.UNCERTAIN,
        ),
        authorizer=PermissionAuthorizer(reader=_AclReader({"resource-1"})),
        evidence_verifier=EvidenceVerifier(
            reader=_EvidenceReader(
                {candidate.source_ref_id: _record(candidate, section, revision)}
            )
        ),
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader({"resource-1": revision}),
        structure_reader=_StructureReader(
            DocumentStructureResult(revision=revision, sections=[section])
        ),
        state_store=_StateStore(),
    )

    result = await locator.locate(
        LocateRequest(
            session_id="session-1",
            semantic_query="灰区问题",
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert result.decision is RankDecision.UNCERTAIN
    assert result.sections[0].evidence[0].source_ref_id == candidate.source_ref_id


@pytest.mark.asyncio
async def test_locate_rejects_revision_change_after_evidence_verification():
    revision = _revision()
    changed_revision = _revision()
    changed_revision.content_revision = "revision-2"
    section = _section("section-1")
    candidate = _candidate("chunk-1", block_id="block-1")
    locator = ReadingEntryLocator(
        embedding_client=_EmbeddingClient(calls=[]),
        candidate_search=_CandidateSearch([candidate]),
        ranking_pipeline=_RankingPipeline([_candidate_id(candidate)]),
        authorizer=PermissionAuthorizer(reader=_AclReader({"resource-1"})),
        evidence_verifier=EvidenceVerifier(
            reader=_EvidenceReader(
                {candidate.source_ref_id: _record(candidate, section, revision)}
            )
        ),
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader({"resource-1": revision}),
        structure_reader=_StructureReader(
            DocumentStructureResult(revision=changed_revision, sections=[section])
        ),
        state_store=_StateStore(),
    )

    with pytest.raises(LocateError, match="changed revision during locate"):
        await locator.locate(
            LocateRequest(
                session_id="session-1",
                semantic_query="问题",
                permission_scope=PermissionScope(user_id="user-1"),
            )
        )
