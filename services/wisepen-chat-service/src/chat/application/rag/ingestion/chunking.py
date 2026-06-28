from __future__ import annotations

from chat.application.rag.ingestion.models import (
    RagChildChunk,
    RagChunkingResult,
    RagParentChunk,
)
from chat.application.utils.chunking_engine import ChunkDocument, ChunkLevel, ChunkingEngine
from chat.application.utils.chunking_engine.registry import (
    NESTED_MARKDOWN_PIPELINE_NAME,
    get_chunking_pipeline,
)


class RagChunkingService:
    """把已取得的 Markdown 正文接入 RAG 父子分块链路。"""

    __slots__ = ("_engine", "_pipeline_name")

    def __init__(
        self,
        *,
        engine: ChunkingEngine | None = None,
        pipeline_name: str = NESTED_MARKDOWN_PIPELINE_NAME,
    ) -> None:
        self._engine = engine or ChunkingEngine()
        self._pipeline_name = pipeline_name

    def chunk(
        self,
        *,
        markdown: str,
        document_id: str = "",
        title: str = "",
    ) -> RagChunkingResult:
        result = self._engine.chunk(
            document=ChunkDocument(
                text=markdown,
                document_id=document_id or None,
                content_type="text/markdown",
                title=title or None,
            ),
            pipeline=get_chunking_pipeline(self._pipeline_name),
        )

        parent_chunks: list[RagParentChunk] = []
        child_chunks: list[RagChildChunk] = []

        for chunk in result.chunks:
            if chunk.level == ChunkLevel.SEARCH:
                child_chunks.append(RagChildChunk.from_chunk(chunk))
            else:
                parent_chunks.append(RagParentChunk.from_chunk(chunk))

        return RagChunkingResult(
            parent_chunks=tuple(parent_chunks),
            child_chunks=tuple(child_chunks),
            pipeline=result.pipeline,
        )
