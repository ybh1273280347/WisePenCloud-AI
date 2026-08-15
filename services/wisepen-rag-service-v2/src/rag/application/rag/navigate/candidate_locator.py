"""根据自然语言问题发现已核验的 Section 阅读入口。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import KnowledgeNode, KnowledgeNodeKind
from rag.domain.models.provenance import SourceEvidence
from rag.domain.models.retrieval import RetrievalCandidate
from rag.domain.repositories.mongo import PublishedResourceReader
from rag.domain.repositories.neo4j import GraphSeedBlock, KnowledgeGraphRepository
from rag.domain.repositories.qdrant.candidate_searcher import CandidateSearcher
from rag.domain.repositories.redis.navigation_state_store import NavigationStateStore
from rag.utils.ranking import (
    RankCandidate,
    RankDecision,
    RankingPipeline,
    RankQuery,
    RankRequest,
    ScoreSignal,
    ScoreSignalKind,
)

from rag.application.rag.navigate.evidence_verifiers import SourceEvidenceVerifier

if TYPE_CHECKING:
    from rag.utils.llm_clients.embedding import EmbeddingClient


@dataclass(slots=True)
class LocateRequest:
    """LOCATE 的可信请求事实，调用方已完成公开入口和字符串边界校验。"""

    session_id: str
    semantic_query: str
    permission_scope: PermissionScope
    lexical_query: str | None = None
    max_results: int = 10
    candidate_limit: int = 80


@dataclass(slots=True)
class LocateResult:
    """一次 LOCATE 的排序结论、已核验入口与后续 navigation state。"""

    state_id: str
    retrieval_status: RankDecision
    nodes: list[KnowledgeNode] = field(default_factory=list)
    sections: list[RetrievedSectionView] = field(default_factory=list)


class LocateError(RuntimeError):
    """LOCATE 输入或模型返回不满足能力契约。"""


@dataclass(slots=True)
class MatchRangeView:
    """相对于 ``RetrievalReadingBlockView.text`` 的 Python 字符半开区间。"""

    start_offset: int
    end_offset: int


@dataclass(slots=True)
class RetrievalMatchView:
    """触发 ReadingBlock 提升的检索 chunk 锚点，不重复返回 chunk 文本。"""

    chunk_id: str
    source_ref_id: str
    ranges: list[MatchRangeView] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalReadingBlockView:
    """检索命中后提升出的完整 ReadingBlock 正文及紧凑页范围。"""

    reading_block_id: str
    text: str
    page_labels: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)
    matches: list[RetrievalMatchView] = field(default_factory=list)


@dataclass(slots=True)
class RetrievedSectionView:
    """承载命中 ReadingBlock；flat text 使用 synthetic Section 作为读取锚点。"""

    resource_id: str
    section_id: str
    title: str
    section_path: str
    reading_blocks: list[RetrievalReadingBlockView] = field(default_factory=list)


class ReadingCandidateLocator:
    """编排召回、精排、回源核验与 Section 阅读入口的创建。"""

    __slots__ = (
        "_authorizer",
        "_candidate_search",
        "_embedding_client",
        "_evidence_verifier",
        "_knowledge_graph",
        "_published_resources",
        "_ranking_pipeline",
        "_state_store",
    )

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        candidate_search: CandidateSearcher,
        ranking_pipeline: RankingPipeline,
        authorizer: PermissionAuthorizer,
        evidence_verifier: SourceEvidenceVerifier,
        knowledge_graph: KnowledgeGraphRepository,
        published_resources: PublishedResourceReader,
        state_store: NavigationStateStore,
    ) -> None:
        self._embedding_client = embedding_client
        self._candidate_search = candidate_search
        self._ranking_pipeline = ranking_pipeline
        self._authorizer = authorizer
        self._evidence_verifier = evidence_verifier
        self._knowledge_graph = knowledge_graph
        self._published_resources = published_resources
        self._state_store = state_store

    async def locate(self, request: LocateRequest) -> LocateResult:
        """只将已发布且仍可读的候选提升为后续 READ 可用的入口。"""
        # 上游 schema 与鉴权层已经收口了公开入口边界，这里只做外部模型返回形状校验。
        semantic_query = request.semantic_query
        lexical_query = (
            semantic_query if request.lexical_query is None else request.lexical_query
        )

        embedding = await self._embedding_client.aembed([semantic_query])
        if len(embedding.embeddings) != 1:
            raise LocateError("query embedding response must contain one vector")

        candidates = await self._candidate_search.search(
            lexical_query=lexical_query,
            semantic_vector=embedding.embeddings[0],
            permission_scope=request.permission_scope,
            limit=request.candidate_limit,
        )
        candidates = await self._filter_readable_candidates(
            candidates,
            request.permission_scope,
        )
        candidates = await self._filter_published_candidates(candidates)
        if not candidates:
            return await self._create_empty_result(request)

        ranking = await self._ranking_pipeline.arank(
            RankRequest(
                query=RankQuery(text=semantic_query),
                candidates=tuple(
                    RankCandidate(
                        candidate_id=_candidate_key(candidate),
                        text=(
                            " > ".join(candidate.section_path)
                            + "\n"
                            + candidate.raw_text
                        ),
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
        ranked_candidates: list[RetrievalCandidate] = []
        selected_block_keys: set[tuple[str, str]] = set()
        for ranked in ranking.ranked:
            candidate = candidates_by_id.get(ranked.candidate_id)
            if candidate is None:
                raise LocateError(
                    f"ranking returned unknown candidate {ranked.candidate_id}"
                )
            ranked_candidates.append(candidate)
            block_key = (candidate.resource_id, candidate.reading_block_id)
            if (
                block_key not in selected_block_keys
                and len(selected_block_keys) < request.max_results
            ):
                selected_block_keys.add(block_key)

        selected = [
            candidate
            for candidate in ranked_candidates
            if (candidate.resource_id, candidate.reading_block_id)
            in selected_block_keys
        ]
        if not selected:
            return await self._create_empty_result(request)

        records = await self._verify_selected(selected)
        readable_records = await self._filter_readable_evidence(
            records,
            request.permission_scope,
        )
        sections = _build_retrieved_section_views(readable_records)
        # seed 的候选范围属于模型实际读到的完整 ReadingBlock；检索 span 只用于
        # 块内 mention 排序，不能继续充当图谱来源过滤条件。
        seed_blocks: dict[tuple[str, str, str], GraphSeedBlock] = {}
        for record in readable_records:
            source_ref = record.source_ref
            key = (
                source_ref.resource_id,
                source_ref.content_revision,
                source_ref.reading_block_id,
            )
            block = seed_blocks.setdefault(
                key,
                GraphSeedBlock(
                    resource_id=source_ref.resource_id,
                    content_revision=source_ref.content_revision,
                    reading_block_id=source_ref.reading_block_id,
                    rank=len(seed_blocks),
                ),
            )
            for span in source_ref.source_spans:
                if span not in block.matched_source_spans:
                    block.matched_source_spans.append(span)
        # 禁用图谱旁路时，这里找不到任何节点，最终不会展示任何图谱入口。
        nodes = await self._knowledge_graph.find_nodes(
            reading_blocks=list(seed_blocks.values()),
            permission_scope=request.permission_scope,
            limit=request.max_results,
        )
        nodes = await self._filter_readable_nodes(nodes, request.permission_scope)
        state = await self._state_store.create(
            user_id=request.permission_scope.user_id,
            session_id=request.session_id,
            known_node_ids=[node.node_id for node in nodes],
        )
        return LocateResult(
            state_id=state.state_id,
            retrieval_status=ranking.decision,
            nodes=nodes,
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

    async def _filter_published_candidates(
        self,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        published_revisions: dict[str, str] = {}
        for resource_id in dict.fromkeys(
            candidate.resource_id for candidate in candidates
        ):
            content_revision = (
                await self._published_resources.get_content_revision(resource_id)
            )
            if content_revision is not None:
                published_revisions[resource_id] = content_revision
        return [
            candidate
            for candidate in candidates
            if published_revisions.get(candidate.resource_id)
            == candidate.content_revision
        ]

    async def _filter_readable_evidence(
        self,
        evidence: Sequence[SourceEvidence],
        permission_scope: PermissionScope,
    ) -> list[SourceEvidence]:
        """图反查前复查证据资源，避免沿用召回开始时的 ACL 快照。"""
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (record.source_ref.resource_id for record in evidence),
                scope=permission_scope,
            )
        )
        return [
            record
            for record in evidence
            if record.source_ref.resource_id in readable_resource_ids
        ]

    async def _filter_readable_nodes(
        self,
        nodes: Sequence[KnowledgeNode],
        permission_scope: PermissionScope,
    ) -> list[KnowledgeNode]:
        resource_ids = [
            node.resource_id
            for node in nodes
            if node.kind is KnowledgeNodeKind.RESOURCE and node.resource_id is not None
        ]
        if not resource_ids:
            return list(nodes)

        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                resource_ids,
                scope=permission_scope,
            )
        )
        return [
            node
            for node in nodes
            if node.kind is not KnowledgeNodeKind.RESOURCE
            or node.resource_id in readable_resource_ids
        ]

    async def _verify_selected(
        self,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[SourceEvidence]:
        # VERIFY 按资源和 revision 回源，跨资源候选必须分别核验。
        candidates_by_revision: dict[tuple[str, str], list[RetrievalCandidate]] = {}
        for candidate in candidates:
            candidates_by_revision.setdefault(
                (candidate.resource_id, candidate.content_revision),
                [],
            ).append(candidate)

        records_by_ref_id: dict[str, SourceEvidence] = {}
        for grouped_candidates in candidates_by_revision.values():
            verified = await self._evidence_verifier.verify_retrieval_candidates(
                grouped_candidates
            )
            records_by_ref_id.update(
                {record.source_ref.ref_id: record for record in verified}
            )
        return [records_by_ref_id[candidate.source_ref_id] for candidate in candidates]

    async def _create_empty_result(
        self,
        request: LocateRequest,
    ) -> LocateResult:
        state = await self._state_store.create(
            user_id=request.permission_scope.user_id,
            session_id=request.session_id,
            known_node_ids=[],
        )
        return LocateResult(
            state_id=state.state_id,
            retrieval_status=RankDecision.IRRELEVANT,
        )


def _candidate_key(candidate: RetrievalCandidate) -> str:
    """给排序管线提供跨资源稳定且不碰撞的候选身份。"""
    return (
        f"{candidate.resource_id}\0{candidate.content_revision}\0{candidate.chunk_id}"
    )


def _build_retrieved_section_views(
    records: list[SourceEvidence],
) -> list[RetrievedSectionView]:
    """按首次命中顺序把核验证据提升并归组为完整 ReadingBlock。"""
    sections: dict[tuple[str, str], RetrievedSectionView] = {}
    blocks: dict[tuple[str, str], RetrievalReadingBlockView] = {}

    for record in records:
        section_key = (record.source_ref.resource_id, record.section.section_id)
        section_view = sections.setdefault(
            section_key,
            RetrievedSectionView(
                resource_id=record.source_ref.resource_id,
                section_id=record.section.section_id,
                title=record.section.title,
                section_path=" > ".join(record.section.section_path),
            ),
        )
        block_key = (record.source_ref.resource_id, record.reading_block.block_id)
        block_view = blocks.get(block_key)
        if block_view is None:
            block_view = RetrievalReadingBlockView(
                reading_block_id=record.reading_block.block_id,
                text=record.reading_block.raw_text,
                page_labels=record.reading_block.page_labels,
                anchor_labels=record.reading_block.anchor_labels,
            )
            blocks[block_key] = block_view
            section_view.reading_blocks.append(block_view)
        block_view.matches.append(
            RetrievalMatchView(
                chunk_id=record.source_ref.chunk_id,
                source_ref_id=record.source_ref.ref_id,
                ranges=_relative_match_ranges(record),
            )
        )

    return list(sections.values())


def _relative_match_ranges(record: SourceEvidence) -> list[MatchRangeView]:
    """把权威 source spans 映射到 ReadingBlock 拼接文本的相对字符坐标。"""
    ranges: list[MatchRangeView] = []
    block_offset = 0
    for index, block_span in enumerate(record.reading_block.source_spans):
        for match_span in record.source_ref.source_spans:
            start = max(block_span.start_offset, match_span.start_offset)
            end = min(block_span.end_offset, match_span.end_offset)
            if start < end:
                ranges.append(
                    MatchRangeView(
                        start_offset=block_offset + start - block_span.start_offset,
                        end_offset=block_offset + end - block_span.start_offset,
                    )
                )
        block_offset += block_span.end_offset - block_span.start_offset
        if index + 1 < len(record.reading_block.source_spans):
            block_offset += 2
    if not ranges:
        raise ValueError(
            f"source ref {record.source_ref.ref_id} is outside its ReadingBlock"
        )
    return ranges
