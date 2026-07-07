from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chat.application.rag.ingestion.models import RagChildChunk, RagParentChunk


class RagCorpusRepository(Protocol):
    async def upsert_document(
            self,
            *,
            resource_id: str,
            document_version: str,
            parent_chunks: tuple[RagParentChunk, ...],
            child_chunks: tuple[RagChildChunk, ...],
    ) -> None:
        ...

    async def load_child_chunks(
            self,
            chunk_ids: tuple[str, ...],
    ) -> tuple[RagChildChunk, ...]:
        ...

    async def load_parent_chunks(
            self,
            chunk_ids: tuple[str, ...],
    ) -> tuple[RagParentChunk, ...]:
        ...
