"""根据自然语言问题发现已核验的 Section 阅读入口。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.verify import EvidenceVerifier
from rag.domain.acl import PermissionScope
from rag.domain.document_structure import Section
from rag.domain.evidence import EvidenceCandidate, EvidenceRecord
from rag.domain.navigation import KnownSection
from rag.domain.read_content import DocumentStructureResult, SectionFrontier
from rag.domain.repositories.applied_revision_reader import AppliedRevisionReader
from rag.domain.repositories.applied_structure_reader import AppliedStructureReader
from rag.domain.repositories.candidate_search import CandidateSearch
from rag.domain.repositories.navigation_state_store import NavigationStateStore
from rag.domain.retrieval import (
    CandidateSearchRequest,
    RetrievalCandidate,
    RetrievalChunk,
)
from rag.utils.ranking import (
    RankCandidate,
    RankDecision,
    RankingPipeline,
    RankQuery,
    RankRequest,
    ScoreSignal,
    ScoreSignalKind,
)

if TYPE_CHECKING:
    from rag.utils.llm_clients.embedding import EmbeddingClient


@dataclass(slots=True)
class LocateRequest:
    """LOCATE 的可信请求事实，调用方已完成身份和数量边界校验。"""

    session_id: str
    semantic_query: str
    permission_scope: PermissionScope
    lexical_query: str | None = None
    resource_ids: list[str] = field(default_factory=list)
    max_results: int = 10
    candidate_limit: int = 80


@dataclass(slots=True)
class LocatedEvidence:
    """一个已核验 ReadingBlock 命中的权威证据。"""

    source_ref_id: str
    reading_block_id: str
    source_text: str


@dataclass(slots=True)
class LocatedSection:
    """LOCATE 发现的 Section 入口及命中证据和可导航 frontier。"""

    resource_id: str
    content_revision: str
    section: Section
    frontier: SectionFrontier
    evidence: list[LocatedEvidence] = field(default_factory=list)


@dataclass(slots=True)
class LocateResult:
    """一次 LOCATE 的排序结论、已核验入口与后续 navigation state。"""

    state_id: str
    decision: RankDecision
    sections: list[LocatedSection] = field(default_factory=list)


class LocateError(RuntimeError):
    """LOCATE 输入或模型返回不满足能力契约。"""


class ReadingEntryLocator:
    """编排召回、精排、回源核验与 Section 阅读入口的创建。"""

    __slots__ = (
        "_authorizer",
        "_candidate_search",
        "_embedding_client",
        "_evidence_verifier",
        "_ranking_pipeline",
        "_revision_reader",
        "_state_store",
        "_structure_reader",
    )

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        candidate_search: CandidateSearch,
        ranking_pipeline: RankingPipeline,
        authorizer: PermissionAuthorizer,
        evidence_verifier: EvidenceVerifier,
        revision_reader: AppliedRevisionReader,
        structure_reader: AppliedStructureReader,
        state_store: NavigationStateStore,
    ) -> None:
        self._embedding_client = embedding_client
        self._candidate_search = candidate_search
        self._ranking_pipeline = ranking_pipeline
        self._authorizer = authorizer
        self._evidence_verifier = evidence_verifier
        self._revision_reader = revision_reader
        self._structure_reader = structure_reader
        self._state_store = state_store

    async def locate(self, request: LocateRequest) -> LocateResult:
        """只将 applied 且仍可读的候选提升为后续 READ 可用的入口。"""
        semantic_query = request.semantic_query.strip()
        if not semantic_query:
            raise LocateError("semantic_query must not be empty")
        lexical_query = (
            semantic_query
            if request.lexical_query is None
            else request.lexical_query.strip()
        )
        if not lexical_query:
            raise LocateError("lexical_query must not be empty when provided")
        if not request.permission_scope.user_id.strip():
            raise LocateError("permission scope user_id must not be empty")
        if request.max_results <= 0 or request.candidate_limit <= 0:
            return await self._create_empty_result(request, semantic_query)

        embedding = await self._embedding_client.aembed([semantic_query])
        if len(embedding.embeddings) != 1:
            raise LocateError("query embedding response must contain one vector")

        candidates = await self._candidate_search.search(
            CandidateSearchRequest(
                lexical_query=lexical_query,
                semantic_vector=embedding.embeddings[0],
                permission_scope=request.permission_scope,
                resource_ids=list(dict.fromkeys(request.resource_ids)),
                limit=request.candidate_limit,
            )
        )
        candidates = await self._filter_readable_candidates(
            candidates,
            request.permission_scope,
        )
        candidates = await self._filter_applied_candidates(candidates)
        if not candidates:
            return await self._create_empty_result(request, semantic_query)

        ranking = await self._ranking_pipeline.arank(
            RankRequest(
                query=RankQuery(text=semantic_query),
                candidates=tuple(
                    RankCandidate(
                        candidate_id=_candidate_key(candidate),
                        text=candidate.raw_text,
                        fields={
                            "section": " > ".join(candidate.section_path),
                            "anchor": "\n".join(candidate.anchor_labels),
                        },
                        prior_rank=index,
                        group_key=candidate.resource_id,
                    )
                    for index, candidate in enumerate(candidates, start=1)
                ),
                signals=tuple(
                    ScoreSignal(
                        candidate_id=_candidate_key(candidate),
                        name="qdrant:rrf",
                        value=candidate.score,
                        kind=ScoreSignalKind.PRIOR,
                        rank=index,
                    )
                    for index, candidate in enumerate(candidates, start=1)
                ),
                top_k=request.candidate_limit,
                candidate_limit=request.candidate_limit,
            )
        )
        if ranking.decision is None:
            raise LocateError("ranking pipeline did not produce a relevance decision")

        candidates_by_id = {
            _candidate_key(candidate): candidate for candidate in candidates
        }
        selected: list[RetrievalCandidate] = []
        seen_blocks: set[tuple[str, str]] = set()
        for ranked in ranking.ranked:
            candidate = candidates_by_id.get(ranked.candidate_id)
            if candidate is None:
                raise LocateError(f"ranking returned unknown candidate {ranked.candidate_id}")
            block_key = (candidate.resource_id, candidate.reading_block_id)
            if block_key in seen_blocks:
                continue
            seen_blocks.add(block_key)
            selected.append(candidate)
            if len(selected) == request.max_results:
                break

        records = await self._verify_selected(selected)
        sections = await self._build_sections(records)
        state = await self._state_store.create(
            user_id=request.permission_scope.user_id,
            session_id=request.session_id,
            root_query=semantic_query,
            known_sections=_known_sections(sections),
            known_node_ids=[],
        )
        return LocateResult(
            state_id=state.state_id,
            decision=ranking.decision,
            sections=sections,
        )

    async def _filter_readable_candidates(
        self,
        candidates: Sequence[RetrievalCandidate],
        permission_scope: PermissionScope,
    ) -> list[RetrievalCandidate]:
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (candidate.resource_id for candidate in candidates),
                scope=permission_scope,
            )
        )
        return [
            candidate
            for candidate in candidates
            if candidate.resource_id in readable_resource_ids
        ]

    async def _filter_applied_candidates(
        self,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        applied_revisions: dict[str, str] = {}
        for resource_id in dict.fromkeys(
            candidate.resource_id for candidate in candidates
        ):
            revision = await self._revision_reader.get_applied_revision(resource_id)
            if revision is not None:
                applied_revisions[resource_id] = revision.content_revision
        return [
            candidate
            for candidate in candidates
            if applied_revisions.get(candidate.resource_id)
            == candidate.content_revision
        ]

    async def _verify_selected(
        self,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[EvidenceRecord]:
        # VERIFY 按资源和 revision 回源，跨资源候选必须分别核验。
        candidates_by_revision: dict[tuple[str, str], list[RetrievalCandidate]] = {}
        for candidate in candidates:
            candidates_by_revision.setdefault(
                (candidate.resource_id, candidate.content_revision),
                [],
            ).append(candidate)

        records_by_ref_id: dict[str, EvidenceRecord] = {}
        for grouped_candidates in candidates_by_revision.values():
            verified = await self._evidence_verifier.verify(
                [_evidence_candidate(candidate) for candidate in grouped_candidates]
            )
            records_by_ref_id.update(
                {record.source_ref.ref_id: record for record in verified}
            )
        return [records_by_ref_id[candidate.source_ref_id] for candidate in candidates]

    async def _build_sections(
        self,
        records: Sequence[EvidenceRecord],
    ) -> list[LocatedSection]:
        resource_structures: dict[str, DocumentStructureResult] = {}
        revisions_by_resource = {
            record.revision.resource_id: record.revision.content_revision
            for record in records
        }
        for resource_id, content_revision in revisions_by_resource.items():
            structure = await self._structure_reader.get_applied_document_structure(resource_id)
            if structure is None:
                raise LocateError(f"resource {resource_id} has no applied structure")
            if structure.revision.content_revision != content_revision:
                raise LocateError(
                    f"resource {resource_id} changed revision during locate"
                )
            resource_structures[resource_id] = structure

        grouped: dict[tuple[str, str], list[EvidenceRecord]] = {}
        for record in records:
            grouped.setdefault(
                (record.revision.resource_id, record.section.section_id),
                [],
            ).append(record)

        entries: list[LocatedSection] = []
        for (resource_id, section_id), section_records in grouped.items():
            structure = resource_structures[resource_id]
            sections_by_id = {
                section.section_id: section for section in structure.sections
            }
            siblings_by_parent: dict[str | None, list[Section]] = {}
            for section in structure.sections:
                siblings_by_parent.setdefault(section.parent_section_id, []).append(section)
            for siblings in siblings_by_parent.values():
                siblings.sort(key=lambda section: section.ordinal)
            section = sections_by_id.get(section_id)
            if section is None:
                raise LocateError(f"verified section {section_id} is absent from structure")
            siblings = siblings_by_parent[section.parent_section_id]
            index = next(
                index
                for index, sibling in enumerate(siblings)
                if sibling.section_id == section_id
            )
            entries.append(
                LocatedSection(
                    resource_id=resource_id,
                    content_revision=structure.revision.content_revision,
                    section=section,
                    frontier=SectionFrontier(
                        parent=sections_by_id.get(section.parent_section_id),
                        previous=siblings[index - 1] if index else None,
                        next=(
                            siblings[index + 1]
                            if index + 1 < len(siblings)
                            else None
                        ),
                        children=siblings_by_parent.get(section.section_id, []),
                    ),
                    evidence=[
                        LocatedEvidence(
                            source_ref_id=record.source_ref.ref_id,
                            reading_block_id=record.reading_block.block_id,
                            source_text=record.source_text,
                        )
                        for record in section_records
                    ],
                )
            )
        return entries

    async def _create_empty_result(
        self,
        request: LocateRequest,
        semantic_query: str,
    ) -> LocateResult:
        state = await self._state_store.create(
            user_id=request.permission_scope.user_id,
            session_id=request.session_id,
            root_query=semantic_query,
            known_sections={},
            known_node_ids=[],
        )
        return LocateResult(
            state_id=state.state_id,
            decision=RankDecision.IRRELEVANT,
        )


def _evidence_candidate(candidate: RetrievalCandidate) -> EvidenceCandidate:
    return EvidenceCandidate(
        resource_id=candidate.resource_id,
        content_revision=candidate.content_revision,
        source_ref_id=candidate.source_ref_id,
        chunk=RetrievalChunk(
            chunk_id=candidate.chunk_id,
            reading_block_id=candidate.reading_block_id,
            section_id=candidate.section_id,
            section_path=list(candidate.section_path),
            raw_text=candidate.raw_text,
            index_text=candidate.raw_text,
            source_spans=list(candidate.source_spans),
            page_labels=list(candidate.page_labels),
            anchor_labels=list(candidate.anchor_labels),
        ),
    )


def _candidate_key(candidate: RetrievalCandidate) -> str:
    """给排序管线提供跨资源稳定且不碰撞的候选身份。"""
    return (
        f"{candidate.resource_id}\0{candidate.content_revision}\0{candidate.chunk_id}"
    )


def _known_sections(sections: Sequence[LocatedSection]) -> dict[str, KnownSection]:
    known: dict[str, KnownSection] = {}
    for entry in sections:
        for section in (
            entry.section,
            entry.frontier.parent,
            entry.frontier.previous,
            entry.frontier.next,
            *entry.frontier.children,
        ):
            if section is not None:
                known[section.section_id] = KnownSection(
                    resource_id=entry.resource_id,
                    content_revision=entry.content_revision,
                )
    return known
