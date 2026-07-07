from __future__ import annotations

from datetime import datetime, timezone

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from chat.application.utils.chunking_engine.models import IndexKind


class RagChunkExtraIndexDocument(BaseModel):
    index_name: str = Field(..., description="完整索引名")
    index_kind: IndexKind = Field(..., description="索引类型")
    start_offset: int | None = Field(default=None, description="索引覆盖的原文起始 offset")
    end_offset: int | None = Field(default=None, description="索引覆盖的原文结束 offset")
    section_path: list[str] = Field(default_factory=list, description="章节路径")
    page_label: str | None = Field(default=None, description="页码标签")
    anchor_label: str | None = Field(default=None, description="锚点标签")


class RagParentChunkDocument(Document):
    """RAG 父块事实表。"""

    resource_id: str = Field(..., description="资源 ID")
    document_version: str = Field(..., description="文档版本")
    chunk_id: str = Field(..., description="父块 ID")
    text: str = Field(..., description="父块原文")
    chunk_index: int = Field(..., description="文档内顺序索引")
    start_offset: int | None = Field(default=None, description="Markdown 起始 offset")
    end_offset: int | None = Field(default=None, description="Markdown 结束 offset")
    extra_indexes: list[RagChunkExtraIndexDocument] = Field(default_factory=list, description="定位索引")
    content_hash: str = Field(default="", description="父块原文 hash")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "wisepen_rag_parent_chunks"
        indexes = [
            IndexModel(
                [("resource_id", ASCENDING), ("document_version", ASCENDING), ("chunk_id", ASCENDING)],
                name="uniq_rag_parent_chunk_resource_version_chunk",
                unique=True,
            ),
            IndexModel(
                [("resource_id", ASCENDING), ("document_version", ASCENDING), ("chunk_index", ASCENDING)],
                name="idx_rag_parent_chunk_resource_version_order",
            ),
        ]


class RagChildChunkDocument(Document):
    """RAG 子块事实表。"""

    resource_id: str = Field(..., description="资源 ID")
    document_version: str = Field(..., description="文档版本")
    chunk_id: str = Field(..., description="子块 ID")
    parent_chunk_id: str = Field(..., description="关联父块 ID")
    text: str = Field(..., description="子块原文")
    chunk_index: int = Field(..., description="文档内顺序索引")
    start_offset: int | None = Field(default=None, description="Markdown 起始 offset")
    end_offset: int | None = Field(default=None, description="Markdown 结束 offset")
    extra_indexes: list[RagChunkExtraIndexDocument] = Field(default_factory=list, description="定位索引")
    content_hash: str = Field(default="", description="子块原文 hash")
    indexing_context: str = Field(default="", description="Context Indexing 上下文补充")
    indexing_text: str = Field(default="", description="用于检索索引的文本")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "wisepen_rag_child_chunks"
        indexes = [
            IndexModel(
                [("resource_id", ASCENDING), ("document_version", ASCENDING), ("chunk_id", ASCENDING)],
                name="uniq_rag_child_chunk_resource_version_chunk",
                unique=True,
            ),
            IndexModel(
                [("resource_id", ASCENDING), ("document_version", ASCENDING), ("chunk_index", ASCENDING)],
                name="idx_rag_child_chunk_resource_version_order",
            ),
            IndexModel(
                [("parent_chunk_id", ASCENDING)],
                name="idx_rag_child_chunk_parent",
            ),
        ]
