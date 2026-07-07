from __future__ import annotations

from datetime import datetime, timezone

from chat.application.rag.ingestion.models import (
    RagChildChunk,
    RagChunkExtraIndex,
    RagParentChunk,
)
from chat.domain.entities.rag_corpus import (
    RagChildChunkDocument,
    RagChunkExtraIndexDocument,
    RagParentChunkDocument,
)


class MongoRagCorpusRepository:
    """MongoDB RAG Corpus 事实仓储。"""

    async def upsert_document(
            self,
            *,
            resource_id: str,
            document_version: str,
            parent_chunks: tuple[RagParentChunk, ...],
            child_chunks: tuple[RagChildChunk, ...],
    ) -> None:
        now = datetime.now(timezone.utc)
        await RagParentChunkDocument.find(
            RagParentChunkDocument.resource_id == resource_id,
            RagParentChunkDocument.document_version == document_version,
        ).delete()
        await RagChildChunkDocument.find(
            RagChildChunkDocument.resource_id == resource_id,
            RagChildChunkDocument.document_version == document_version,
        ).delete()

        parent_documents = [
            RagParentChunkDocument(
                resource_id=resource_id,
                document_version=document_version,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                chunk_index=chunk.chunk_index,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                extra_indexes=_to_extra_index_documents(chunk.extra_indexes),
                content_hash=chunk.content_hash,
                created_at=now,
                updated_at=now,
            )
            for chunk in parent_chunks
        ]
        child_documents = [
            RagChildChunkDocument(
                resource_id=resource_id,
                document_version=document_version,
                chunk_id=chunk.chunk_id,
                parent_chunk_id=chunk.parent_chunk_id,
                text=chunk.text,
                chunk_index=chunk.chunk_index,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                extra_indexes=_to_extra_index_documents(chunk.extra_indexes),
                content_hash=chunk.content_hash,
                indexing_context=chunk.indexing_context,
                indexing_text=chunk.indexing_text,
                created_at=now,
                updated_at=now,
            )
            for chunk in child_chunks
        ]

        if parent_documents:
            await RagParentChunkDocument.insert_many(parent_documents)
        if child_documents:
            await RagChildChunkDocument.insert_many(child_documents)

    async def load_child_chunks(
            self,
            chunk_ids: tuple[str, ...],
    ) -> tuple[RagChildChunk, ...]:
        if not chunk_ids:
            return ()

        documents = await RagChildChunkDocument.find(
            RagChildChunkDocument.chunk_id.in_(chunk_ids)
        ).to_list()
        by_id = {document.chunk_id: document for document in documents}
        return tuple(
            RagChildChunk(
                chunk_id=document.chunk_id,
                text=document.text,
                chunk_index=document.chunk_index,
                parent_chunk_id=document.parent_chunk_id,
                start_offset=document.start_offset,
                end_offset=document.end_offset,
                extra_indexes=_to_extra_indexes(document.extra_indexes),
                content_hash=document.content_hash,
                indexing_context=document.indexing_context,
                indexing_text=document.indexing_text,
            )
            for chunk_id in chunk_ids
            if (document := by_id.get(chunk_id)) is not None
        )

    async def load_parent_chunks(
            self,
            chunk_ids: tuple[str, ...],
    ) -> tuple[RagParentChunk, ...]:
        if not chunk_ids:
            return ()

        documents = await RagParentChunkDocument.find(
            RagParentChunkDocument.chunk_id.in_(chunk_ids)
        ).to_list()
        by_id = {document.chunk_id: document for document in documents}
        return tuple(
            RagParentChunk(
                chunk_id=document.chunk_id,
                text=document.text,
                chunk_index=document.chunk_index,
                start_offset=document.start_offset,
                end_offset=document.end_offset,
                extra_indexes=_to_extra_indexes(document.extra_indexes),
                content_hash=document.content_hash,
            )
            for chunk_id in chunk_ids
            if (document := by_id.get(chunk_id)) is not None
        )


def _to_extra_index_documents(
        indexes: tuple[RagChunkExtraIndex, ...],
) -> list[RagChunkExtraIndexDocument]:
    return [
        RagChunkExtraIndexDocument(
            index_name=index.index_name,
            index_kind=index.index_kind,
            start_offset=index.start_offset,
            end_offset=index.end_offset,
            section_path=list(index.section_path),
            page_label=index.page_label,
            anchor_label=index.anchor_label,
        )
        for index in indexes
    ]


def _to_extra_indexes(
        documents: list[RagChunkExtraIndexDocument],
) -> tuple[RagChunkExtraIndex, ...]:
    return tuple(
        RagChunkExtraIndex(
            index_name=document.index_name,
            index_kind=document.index_kind,
            start_offset=document.start_offset,
            end_offset=document.end_offset,
            section_path=tuple(document.section_path),
            page_label=document.page_label,
            anchor_label=document.anchor_label,
        )
        for document in documents
    )
