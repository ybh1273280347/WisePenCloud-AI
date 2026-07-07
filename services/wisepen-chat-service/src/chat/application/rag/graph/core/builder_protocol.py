from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chat.application.rag.ingestion.models import RagChildChunk, RagParentChunk


class RagKnowledgeGraphBuilder(Protocol):
    async def upsert_document_graph(
            self,
            *,
            parent_chunks: tuple[RagParentChunk, ...],
            child_chunks: tuple[RagChildChunk, ...],
            dense_vectors: dict[str, list[float]],
            resource_id: str,
            document_version: str,
            corpus_version: str,
    ) -> None:
        ...
