from __future__ import annotations

from chat.application.rag.ingestion.models import (
    RagChildChunk,
    RagChunkLocator,
    RagChunkingResult,
    RagMarkdownIngestionPayload,
    RagParentChunk,
)
from chat.application.utils.chunking_engine import (
    ChunkDocument,
    ChunkRole,
    ChunkingEngine,
)
from chat.application.utils.chunking_engine.models import ChunkLocator, LocatorKind
from chat.application.utils.chunking_engine.registry import get_chunking_engine


class RagChunkingService:
    """把已取得的 Markdown 正文接入 RAG 父子分块链路。"""

    __slots__ = ("_engine",)

    def __init__(
        self,
        *,
        engine: ChunkingEngine | None = None,
        engine_name: str = "parent_child_markdown",
    ) -> None:
        self._engine = engine or get_chunking_engine(engine_name)

    def chunk(
        self,
        *,
        markdown: str,
        resource_id: str = "",
        document_version: str = "",
    ) -> RagChunkingResult:
        # 复用父子 Markdown 分块引擎：CHILD 供检索，PARENT 用于引用完整上下文。
        result = self._engine.chunk(
            document=ChunkDocument(
                text=markdown,
                content_type="text/markdown",
            ),
        )

        locators_by_chunk = _locators_by_chunk(result.locators)
        parent_chunks: list[RagParentChunk] = []
        child_chunks: list[RagChildChunk] = []

        for chunk in result.chunks:
            locators = locators_by_chunk.get(chunk.chunk_id, ())
            # CHILD 角色作为子块进入检索索引；其余角色作为父块保留完整原文。
            if chunk.role == ChunkRole.CHILD:
                child_chunks.append(
                    RagChildChunk.from_chunk(
                        chunk,
                        locators=locators,
                    )
                )
            else:
                parent_chunks.append(
                    RagParentChunk.from_chunk(
                        chunk,
                        locators=locators,
                    )
                )

        return RagChunkingResult(
            parent_chunks=tuple(parent_chunks),
            child_chunks=tuple(child_chunks),
            pipeline=result.pipeline,
            resource_id=resource_id,
            document_version=document_version,
        )

    def chunk_payload(self, payload: RagMarkdownIngestionPayload) -> RagChunkingResult:
        """按当前非权限入库协议切分一篇 Markdown 文档。"""
        return self.chunk(
            markdown=payload.markdown,
            resource_id=payload.resource_id,
            document_version=payload.document_version,
        )


def _locators_by_chunk(
    locators: tuple[ChunkLocator, ...],
) -> dict[str, tuple[RagChunkLocator, ...]]:
    """把 chunking engine 产出的全局定位项，按 chunk_id 分组投影到 RAG 索引模型。

    只保留页码、章节、锚点三类定位项，它们共同用于后续引用定位和上下文展示。
    """
    locators_by_chunk: dict[str, list[RagChunkLocator]] = {}
    for locator in locators:
        projected = RagChunkLocator.from_chunk_locator(locator)
        # 一个定位项可能覆盖多个 chunk（例如跨 chunk 的章节标题）。
        for chunk_id in locator.chunk_ids:
            locators_by_chunk.setdefault(chunk_id, []).append(projected)

    return {
        chunk_id: tuple(projected_locators)
        for chunk_id, projected_locators in locators_by_chunk.items()
    }
