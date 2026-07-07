from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from chat.application.rag.ingestion.models import RagChildChunk, RagChunkingResult


@dataclass(frozen=True, slots=True)
class RagChunkingCacheKey:
    document_version: str
    content_hash: str
    pipeline: str
    config_version: str


@dataclass(frozen=True, slots=True)
class RagContextIndexingCacheKey:
    child_content_hash: str
    parent_content_hash: str
    model: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class RagEmbeddingCacheKey:
    text_hash: str
    model: str
    dimensions: int


class RagIngestionDeterministicCache(Protocol):
    async def get_chunking_result(
            self,
            key: RagChunkingCacheKey,
    ) -> RagChunkingResult | None:
        ...

    async def set_chunking_result(
            self,
            key: RagChunkingCacheKey,
            result: RagChunkingResult,
    ) -> None:
        ...

    async def get_context_indexed_child(
            self,
            key: RagContextIndexingCacheKey,
    ) -> RagChildChunk | None:
        ...

    async def set_context_indexed_child(
            self,
            key: RagContextIndexingCacheKey,
            child: RagChildChunk,
    ) -> None:
        ...

    async def get_embedding_vectors(
            self,
            keys: dict[str, RagEmbeddingCacheKey],
    ) -> dict[str, list[float]]:
        ...

    async def set_embedding_vectors(
            self,
            vectors: dict[str, tuple[RagEmbeddingCacheKey, list[float]]],
    ) -> None:
        ...
