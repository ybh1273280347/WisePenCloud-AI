from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from chat.application.rag.acl import RagAclProjectionRepository, RagResourceAclProjection
from chat.application.rag.cache.ingestion_deterministic import (
    RagChunkingCacheKey,
    RagContextIndexingCacheKey,
    RagEmbeddingCacheKey,
    RagIngestionDeterministicCache,
)
from chat.application.rag.ingestion.chunking import RagChunkingService
from chat.application.rag.ingestion.context_indexing import (
    ContextIndexingError,
    ContextIndexingService,
)
from chat.application.rag.ingestion.models import (
    ContextIndexingInput,
    RagChildChunk,
    RagChunkingResult,
    RagMarkdownIngestionPayload,
    RagParentChunk,
)
from chat.core.persistence.elasticsearch import RagElasticRepository
from chat.core.persistence.qdrant import RagQdrantRepository

if TYPE_CHECKING:
    from chat.application.rag.corpus import RagCorpusRepository
    from chat.application.rag.graph import RagKnowledgeGraphBuilder
    from chat.application.rag.graph.core.repository_protocol import RagGraphRepository

_CHUNKING_CONFIG_VERSION = "parent_child_markdown:v1"
_CONTEXT_INDEXING_PROMPT_VERSION = "xml_context_indexing:v1"


@dataclass(frozen=True, slots=True)
class RagMarkdownIngestResult:
    resource_id: str
    document_version: str
    corpus_version: str
    parent_chunks: tuple[RagParentChunk, ...]
    child_chunks: tuple[RagChildChunk, ...]
    pipeline: str
    indexed_child_count: int
    acl_projection: RagResourceAclProjection | None


class RagIngestionRetryableError(RuntimeError):
    """RAG 入库遇到可重试失败，Kafka 消费者应重抛以避免提交 offset。"""


class RagMarkdownIngester:
    """执行 RAG 文档入库主链路。"""

    __slots__ = (
        "_acl_repository",
        "_chunking_service",
        "_context_indexing_service",
        "_corpus_repository",
        "_elastic_repository",
        "_embedding_dimensions",
        "_embedding_client",
        "_embedding_model",
        "_graph_repository",
        "_knowledge_graph_builder",
        "_ingestion_cache",
        "_qdrant_repository",
        "_summary_model",
    )

    def __init__(
            self,
            *,
            chunking_service: RagChunkingService,
            context_indexing_service: ContextIndexingService,
            embedding_client: Any,
            corpus_repository: RagCorpusRepository,
            acl_repository: RagAclProjectionRepository,
            qdrant_repository: RagQdrantRepository,
            elastic_repository: RagElasticRepository,
            graph_repository: RagGraphRepository | None = None,
            knowledge_graph_builder: RagKnowledgeGraphBuilder | None = None,
            ingestion_cache: RagIngestionDeterministicCache | None = None,
            summary_model: str = "",
            embedding_model: str = "",
            embedding_dimensions: int = 0,
    ) -> None:
        self._chunking_service = chunking_service
        self._context_indexing_service = context_indexing_service
        self._embedding_client = embedding_client
        self._corpus_repository = corpus_repository
        self._acl_repository = acl_repository
        self._qdrant_repository = qdrant_repository
        self._elastic_repository = elastic_repository
        self._graph_repository = graph_repository
        self._knowledge_graph_builder = knowledge_graph_builder
        self._ingestion_cache = ingestion_cache
        self._summary_model = summary_model
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions

    async def ingest_markdown(self, payload: RagMarkdownIngestionPayload) -> RagMarkdownIngestResult:
        chunking_result = await self._chunk_payload(payload)
        try:
            child_chunks = await self._build_context_indexed_children(chunking_result)
        except ContextIndexingError as exc:
            raise RagIngestionRetryableError(
                "RAG ingestion failed before indexing because context indexing failed."
            ) from exc
        corpus_version = payload.document_version
        acl_projection = await self._acl_repository.get_projection(payload.resource_id)

        await self._corpus_repository.upsert_document(
            resource_id=payload.resource_id,
            document_version=payload.document_version,
            parent_chunks=chunking_result.parent_chunks,
            child_chunks=child_chunks,
        )

        dense_vectors = await self._embed_children(child_chunks)
        await self._qdrant_repository.upsert_child_chunks(
            child_chunks=child_chunks,
            dense_vectors=dense_vectors,
            resource_id=payload.resource_id,
            document_version=payload.document_version,
            corpus_version=corpus_version,
            acl_projection=acl_projection,
        )
        await self._elastic_repository.upsert_child_chunks(
            child_chunks=child_chunks,
            resource_id=payload.resource_id,
            document_version=payload.document_version,
            corpus_version=corpus_version,
            acl_projection=acl_projection,
        )
        if self._graph_repository is not None:
            await self._graph_repository.delete_document_projection(
                resource_id=payload.resource_id,
                document_version=payload.document_version,
            )
        if self._knowledge_graph_builder is not None:
            await self._knowledge_graph_builder.upsert_document_graph(
                parent_chunks=chunking_result.parent_chunks,
                child_chunks=child_chunks,
                dense_vectors=dense_vectors,
                resource_id=payload.resource_id,
                document_version=payload.document_version,
                corpus_version=corpus_version,
            )
        if self._graph_repository is not None and acl_projection is not None:
            await self._graph_repository.update_acl_projection(acl_projection)

        return RagMarkdownIngestResult(
            resource_id=payload.resource_id,
            document_version=payload.document_version,
            corpus_version=corpus_version,
            parent_chunks=chunking_result.parent_chunks,
            child_chunks=child_chunks,
            pipeline=chunking_result.pipeline,
            indexed_child_count=len(child_chunks),
            acl_projection=acl_projection,
        )

    async def _build_context_indexed_children(
            self,
            chunking_result: RagChunkingResult,
    ) -> tuple[RagChildChunk, ...]:
        parent_text_by_id = {
            parent.chunk_id: parent.text
            for parent in chunking_result.parent_chunks
        }
        indexed_children: list[RagChildChunk] = []
        for child in chunking_result.child_chunks:
            indexed_children.append(
                await self._context_index_child(
                    child=child,
                    parent_text=parent_text_by_id.get(child.parent_chunk_id, ""),
                )
            )
        return tuple(indexed_children)

    async def _embed_children(
            self,
            child_chunks: tuple[RagChildChunk, ...],
    ) -> dict[str, list[float]]:
        if not child_chunks:
            return {}

        cache_keys = {
            child.chunk_id: RagEmbeddingCacheKey(
                text_hash=_hash_text(child.indexing_text or child.text),
                model=self._embedding_model,
                dimensions=self._embedding_dimensions,
            )
            for child in child_chunks
        }
        cached_vectors = (
            await self._ingestion_cache.get_embedding_vectors(cache_keys)
            if self._ingestion_cache is not None
            else {}
        )
        missing_children = tuple(
            child
            for child in child_chunks
            if child.chunk_id not in cached_vectors
        )
        if not missing_children:
            return cached_vectors

        texts = [child.indexing_text or child.text for child in missing_children]
        result = await self._embedding_client.aembed(texts)
        fresh_vectors = {
            child.chunk_id: vector
            for child, vector in zip(missing_children, result.embeddings, strict=True)
        }
        if self._ingestion_cache is not None:
            await self._ingestion_cache.set_embedding_vectors(
                {
                    chunk_id: (cache_keys[chunk_id], vector)
                    for chunk_id, vector in fresh_vectors.items()
                }
            )
        return {**cached_vectors, **fresh_vectors}

    async def _chunk_payload(self, payload: RagMarkdownIngestionPayload) -> RagChunkingResult:
        key = RagChunkingCacheKey(
            document_version=payload.document_version,
            content_hash=_hash_text(payload.markdown),
            pipeline="parent_child_markdown",
            config_version=_CHUNKING_CONFIG_VERSION,
        )
        if self._ingestion_cache is not None:
            cached = await self._ingestion_cache.get_chunking_result(key)
            if cached is not None:
                return RagChunkingResult(
                    parent_chunks=cached.parent_chunks,
                    child_chunks=cached.child_chunks,
                    pipeline=cached.pipeline,
                    resource_id=payload.resource_id,
                    document_version=payload.document_version,
                )

        result = self._chunking_service.chunk_payload(payload)
        if self._ingestion_cache is not None:
            await self._ingestion_cache.set_chunking_result(key, result)
        return result

    async def _context_index_child(
            self,
            *,
            child: RagChildChunk,
            parent_text: str,
    ) -> RagChildChunk:
        key = RagContextIndexingCacheKey(
            child_content_hash=child.content_hash or _hash_text(child.text),
            parent_content_hash=_hash_text(parent_text),
            model=self._summary_model,
            prompt_version=_CONTEXT_INDEXING_PROMPT_VERSION,
        )
        if self._ingestion_cache is not None:
            cached = await self._ingestion_cache.get_context_indexed_child(key)
            if cached is not None:
                return child.with_indexing_context(
                    indexing_context=cached.indexing_context,
                    indexing_text=cached.indexing_text,
                )

        result = await self._context_indexing_service.build(
            ContextIndexingInput(
                parent_text=parent_text,
                child_chunk=child,
            )
        )
        if self._ingestion_cache is not None:
            await self._ingestion_cache.set_context_indexed_child(key, result.child_chunk)
        return result.child_chunk


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
