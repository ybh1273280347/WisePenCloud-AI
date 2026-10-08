"""两路文档召回、请求级 ACL 快照、精排和三路动态父块构建。"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from common.utils.ranking import (
    RankCandidate,
    RankDecision,
    RankingPipeline,
    RankQuery,
    RankRequest,
)

from rag.application.document.context import ContextMigrationRequired
from rag.application.document.models import DocChunk, Document
from rag.application.plugins.core import RagPluginRegistry
from rag.application.retrieval.models import (
    ChunkHit,
    GraphNodeReference,
    HybridRetrieveResult,
)
from rag.domain.acl import PermissionScope
from rag.domain.repositories.acl import ResourceAclRepository
from rag.domain.repositories.doc_chunks import DocChunkRepository
from rag.domain.repositories.document_vectors import (
    DocumentVectorRepository,
    VectorCandidate,
)
from rag.domain.repositories.documents import DocumentRepository
from rag.domain.repositories.graph_fact import GraphFactRepository
from rag.domain.repositories.index_state import ResourceIndexStateRepository
from rag.domain.repositories.metadata_filters import MetadataFilterCondition
from rag.utils import EmbeddingClient

# --- 常量配置 ---

_CANDIDATE_LIMIT = 30


# --- 内部辅助数据类 ---

@dataclass(frozen=True, slots=True)
class _RankedChunk:
    chunk: DocChunk
    rank: int
    score: float


# --- 混合检索器 ---

class HybridRetriever:
    """执行传统 RAG 检索，不隐式进入图谱检索或保存父块。"""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        doc_chunks: DocChunkRepository,
        document_vectors: DocumentVectorRepository,
        index_states: ResourceIndexStateRepository,
        resource_acls: ResourceAclRepository,
        ranking_pipeline: RankingPipeline,
        embedding_client: EmbeddingClient,
        embedding_model: str,
        embedding_dimensions: int,
        embedding_semaphore: asyncio.Semaphore,
        plugin_registry: RagPluginRegistry,
        graph_facts: GraphFactRepository,
    ) -> None:
        self._documents = documents
        self._doc_chunks = doc_chunks
        self._document_vectors = document_vectors
        self._index_states = index_states
        self._resource_acls = resource_acls
        self._ranking_pipeline = ranking_pipeline
        self._embedding_client = embedding_client
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._embedding_semaphore = embedding_semaphore
        self._plugin_registry = plugin_registry
        self._graph_facts = graph_facts

    async def retrieve(
        self,
        query: str,
        top_k: int,
        *,
        scope: PermissionScope,
        plugin_id: str | None = None,
        metadata_filter=None,
    ) -> HybridRetrieveResult:
        """独立召回两路 Top 30，在 Mongo 当前事实和 ACL 快照校验后才产生 Hit。"""
        # 输入校验
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        metadata_filters = _compile_metadata_filters(
            plugin_registry=self._plugin_registry,
            plugin_id=plugin_id,
            metadata_filter=metadata_filter,
        )

        # 1. 生成查询向量并并行检索稠密和BM25
        async with self._embedding_semaphore:
            query_vector = (
                await self._embedding_client.embed(
                    model=self._embedding_model,
                    texts=[query],
                    dimensions=self._embedding_dimensions,
                )
            )[0]
        dense, lexical = await asyncio.gather(
            self._document_vectors.search_dense(
                query_vector=query_vector,
                scope=scope,
                metadata_filters=metadata_filters,
                limit=_CANDIDATE_LIMIT,
            ),
            self._document_vectors.search_bm25(
                query=query,
                scope=scope,
                metadata_filters=metadata_filters,
                limit=_CANDIDATE_LIMIT,
            ),
        )

        # 2. 并集合并候选。这里不对两路 rank 排序；两路结果去重后
        # 全量交给 RankingPipeline，rank 只作为回查审计信号保留。
        candidates = _union_candidates(dense, lexical)
        if not candidates:
            return _empty_result()

        # 3. 加载候选 chunk，并建立本次请求唯一的 active/ACL 快照
        chunks = await self._doc_chunks.get_chunks_by_ids(
            [candidate.chunk_id for candidate in candidates]
        )
        visible_chunks, _documents = await self._load_visible_chunks(chunks, scope=scope)
        if not visible_chunks:
            return _empty_result()

        # 4. 准备精排输入
        chunks_by_id = {chunk.chunk_id: chunk for chunk in visible_chunks}
        ranking_candidates = [
            RankCandidate(
                candidate_id=candidate.chunk_id,
                # 仅使用标题+正文，不包含关键词或前缀（防止污染）
                text=chunks_by_id[candidate.chunk_id].get_full_text(),
                prior_rank=index,
            )
            for index, candidate in enumerate(candidates, start=1)
            if candidate.chunk_id in chunks_by_id
        ]

        # 5. 执行精排
        rank_result = await self._ranking_pipeline.arank(
            RankRequest(
                query=RankQuery(text=query),
                candidates=ranking_candidates,
                top_k=top_k,
                candidate_limit=len(ranking_candidates),
            )
        )
        decision = rank_result.decision or RankDecision.IRRELEVANT
        if decision is RankDecision.IRRELEVANT:
            return _empty_result()

        # 6. 构建命中列表
        ranked_chunks = [
            _RankedChunk(
                chunk=chunks_by_id[item.candidate_id],
                rank=item.rank,
                score=item.score,
            )
            for item in rank_result.ranked
            if item.candidate_id in chunks_by_id
        ]
        hits = [_to_hit(item) for item in ranked_chunks]

        # HTTP 只返回 parents，不能把有命中的检索伪装成成功空结果。
        parents = self._build_dynamic_parents()

        result = HybridRetrieveResult(
            hits=hits,
            parents=parents,
            relevance_decision=decision,
        )
        return await self._attach_seed_nodes(result, ranked_chunks)

    @staticmethod
    def _build_dynamic_parents():
        raise ContextMigrationRequired(
            "dynamic parent construction requires structural ContextExpander integration; "
            "see docs/research/wisepen-rag-chunking-migration-blockers.md"
        )

    async def _attach_seed_nodes(self, result: HybridRetrieveResult, ranked_chunks: list[_RankedChunk]) -> HybridRetrieveResult:
        refs = [
            (item.chunk.resource_id, item.chunk.content_revision, node_id)
            for item in ranked_chunks
            for node_id in item.chunk.extracted_node_ids
        ]
        projections = await self._graph_facts.get_node_projections(refs)
        nodes = {
            (item.resource_id, item.content_revision, item.node.node_id): item.node
            for item in projections
        }
        refs_by_chunk = {
            item.chunk.chunk_id: [
                nodes[key]
                for node_id in item.chunk.extracted_node_ids
                if (key := (item.chunk.resource_id, item.chunk.content_revision, node_id)) in nodes
            ]
            for item in ranked_chunks
        }
        parents = [
            replace(
                parent,
                seed_nodes=_dedupe_seed_nodes(
                    node
                    for chunk_id in parent.matched_chunk_ids
                    for node in refs_by_chunk.get(chunk_id, ())
                ),
            )
            for parent in result.parents
        ]
        return replace(result, parents=parents)

    async def _load_visible_chunks(
        self,
        chunks: Sequence[DocChunk],
        *,
        scope: PermissionScope,
    ) -> tuple[list[DocChunk], Mapping[tuple[str, str], Document]]:
        """过滤掉未发布、无权限或 span 失效的 chunk。"""
        resource_ids = list(dict.fromkeys(chunk.resource_id for chunk in chunks))

        # 并行获取状态和 ACL
        states, resource_acls = await asyncio.gather(
            self._index_states.get_states(resource_ids),
            self._resource_acls.get_resource_acls(resource_ids),
        )

        # 加载活跃 revision 的文档
        active_revisions = [
            (resource_id, state.applied_content_revision)
            for resource_id, state in states.items()
            if state.applied_content_revision is not None
        ]
        documents = await self._documents.get_revisions(active_revisions)

        # 逐 chunk 校验
        visible: list[DocChunk] = []
        for chunk in chunks:
            state = states.get(chunk.resource_id)
            resource_acl = resource_acls.get(chunk.resource_id)
            document = documents.get((chunk.resource_id, chunk.content_revision))
            if (
                state is None
                or state.applied_content_revision != chunk.content_revision
            ):
                continue
            if resource_acl is None or not resource_acl.can_read(scope):
                continue
            if document is None or not chunk.is_valid_for(document):
                continue
            visible.append(chunk)
        return visible, documents


# --- 辅助函数：metadata 过滤 ---

def _compile_metadata_filters(
    *,
    plugin_registry: RagPluginRegistry,
    plugin_id: str | None,
    metadata_filter,
) -> tuple[MetadataFilterCondition, ...]:
    """将垂类声明式过滤编译为索引条件；API 尚未暴露该内部参数。"""
    if metadata_filter is not None and plugin_id is None:
        raise ValueError("metadata_filter requires plugin_id")
    if plugin_id is None:
        return ()
    plugin = plugin_registry.get(plugin_id)
    if plugin is None:
        raise ValueError("RAG plugin is not registered")
    return plugin.compile_filter(metadata_filter)


# --- 辅助函数：候选合并 ---

def _union_candidates(
    dense: Sequence[VectorCandidate],
    lexical: Sequence[VectorCandidate],
) -> list[VectorCandidate]:
    """按 Chunk ID 取并集，保留两路独立 rank，不产生新的排序分数。"""
    by_chunk_id: dict[str, VectorCandidate] = {}
    for candidate in (*dense, *lexical):
        current = by_chunk_id.get(candidate.chunk_id)
        if current is None:
            by_chunk_id[candidate.chunk_id] = candidate
            continue
        # 若 payload 身份冲突则丢弃该候选（索引不一致）
        if (
            current.resource_id != candidate.resource_id
            or current.content_revision != candidate.content_revision
        ):
            by_chunk_id.pop(candidate.chunk_id)
            continue
        # 保留两路 rank，缺失值用0表示未命中
        by_chunk_id[candidate.chunk_id] = VectorCandidate(
            chunk_id=current.chunk_id,
            resource_id=current.resource_id,
            content_revision=current.content_revision,
            dense_rank=current.dense_rank or candidate.dense_rank,
            lexical_rank=current.lexical_rank or candidate.lexical_rank,
        )

    # 不做 min(rank)、RRF 或其他人为粗排。字典顺序只保证结果稳定，
    # 不表达 Dense/BM25 的跨路优先级。
    return list(by_chunk_id.values())


# --- 辅助函数：结果转换 ---

def _to_hit(item: _RankedChunk) -> ChunkHit:
    return ChunkHit(
        chunk_id=item.chunk.chunk_id,
        resource_id=item.chunk.resource_id,
        content_revision=item.chunk.content_revision,
        section_id=item.chunk.section_id,
        section_path=item.chunk.section_path,
        rerank_score=item.score,
        node_ids=list(dict.fromkeys(item.chunk.extracted_node_ids)),
    )


# --- 辅助函数：空结果 ---

def _empty_result() -> HybridRetrieveResult:
    return HybridRetrieveResult(
        hits=[],
        parents=[],
        relevance_decision=RankDecision.IRRELEVANT,
    )


def _dedupe_seed_nodes(nodes) -> list[GraphNodeReference]:
    result: list[GraphNodeReference] = []
    seen: set[str] = set()
    for node in nodes:
        if node.node_id in seen:
            continue
        seen.add(node.node_id)
        result.append(GraphNodeReference(node_id=node.node_id, name=node.name, category=node.category))
    return result
