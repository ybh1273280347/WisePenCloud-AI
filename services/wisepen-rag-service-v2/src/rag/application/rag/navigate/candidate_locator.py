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
from rag.domain.repositories.neo4j import KnowledgeGraphRepository
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

from .source_evidence_verifier import SourceEvidenceVerifier
from .views import (
    KnowledgeNodeView,
    RetrievedSectionView,
    build_retrieved_section_views,
    to_knowledge_node_view,
)

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
    nodes: list[KnowledgeNodeView] = field(default_factory=list)
    sections: list[RetrievedSectionView] = field(default_factory=list)


class LocateError(RuntimeError):
    """LOCATE 输入或模型返回不满足能力契约。"""


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
        sections = build_retrieved_section_views(readable_records)
        nodes = await self._knowledge_graph.find_nodes(
            evidence=readable_records,
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
            nodes=[to_knowledge_node_view(node) for node in nodes],
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
