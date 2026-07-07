from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat.application.rag.acl import RagAclProjectionRepository, RagResourceAclProjection
from chat.application.rag.corpus import RagCorpusRepository
from chat.application.rag.ingestion.chunking import RagChunkingService
from chat.application.rag.ingestion.context_indexing import ContextIndexingService
from chat.application.rag.ingestion.models import (
    ContextIndexingInput,
    RagChildChunk,
    RagChunkingResult,
    RagMarkdownIngestionPayload,
    RagParentChunk,
)
from chat.core.persistence.elasticsearch import RagElasticRepository
from chat.core.persistence.qdrant import RagQdrantRepository


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


class RagMarkdownIngester:
    """执行 RAG 文档入库主链路。"""

    __slots__ = (
        "_acl_repository",
        "_chunking_service",
        "_context_indexing_service",
        "_corpus_repository",
        "_elastic_repository",
        "_embedding_client",
        "_qdrant_repository",
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
    ) -> None:
        self._chunking_service = chunking_service
        self._context_indexing_service = context_indexing_service
        self._embedding_client = embedding_client
        self._corpus_repository = corpus_repository
        self._acl_repository = acl_repository
        self._qdrant_repository = qdrant_repository
        self._elastic_repository = elastic_repository

    async def ingest_markdown(self, payload: RagMarkdownIngestionPayload) -> RagMarkdownIngestResult:
        chunking_result = self._chunking_service.chunk_payload(payload)
        child_chunks = await self._build_context_indexed_children(chunking_result)
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
            result = await self._context_indexing_service.build(
                ContextIndexingInput(
                    parent_text=parent_text_by_id.get(child.parent_chunk_id, ""),
                    child_chunk=child,
                )
            )
            indexed_children.append(result.child_chunk)
        return tuple(indexed_children)

    async def _embed_children(
            self,
            child_chunks: tuple[RagChildChunk, ...],
    ) -> dict[str, list[float]]:
        if not child_chunks:
            return {}

        texts = [
            child.indexing_text or child.text
            for child in child_chunks
        ]
        result = await self._embedding_client.aembed(texts)
        return {
            child.chunk_id: vector
            for child, vector in zip(child_chunks, result.embeddings, strict=True)
        }
