from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from chat.application.utils.chunking_engine.models import Chunk, ChunkIndex, IndexKind


@dataclass(frozen=True, slots=True)
class RagMarkdownIngestionPayload:
    """RAG 当前可确定的 Markdown 入库负载。

    当前协议严格对齐 DocumentReadyMessage：resourceId / version / content。
    权限投影不在当前协议内；等上游权限模型确定后，应作为独立边界接入。
    """

    resource_id: str  # 业务资源根，当前只作为索引归属锚点，不用于权限判断
    document_version: str  # 上游文档版本，用于版本一致性校验
    markdown: str  # DocumentReadyMessage.content，已注入页码标记的 Markdown 正文


@dataclass(frozen=True, slots=True)
class RagChunkExtraIndex:
    """单个 chunk 命中的额外索引投影。"""

    index_name: str  # 完整索引名，如 page:3 / section:快速开始 > 安装
    index_kind: IndexKind  # 索引类型，明确区分页码/章节/锚点
    start_offset: int | None = None  # 索引覆盖的原文起始 offset
    end_offset: int | None = None  # 索引覆盖的原文结束 offset
    section_path: tuple[str, ...] = ()  # section 索引的章节路径
    page_label: str | None = None  # page 索引对应的页码标签
    anchor_label: str | None = None  # anchor 索引对应的锚点标签

    @classmethod
    def from_chunk_index(cls, index: ChunkIndex) -> "RagChunkExtraIndex":
        metadata = index.metadata
        return cls(
            index_name=index.name,
            index_kind=index.kind,
            start_offset=index.start_offset,
            end_offset=index.end_offset,
            section_path=cast(tuple[str, ...] | None, metadata.get("section_path")) or (),
            page_label=cast(str | None, metadata.get("page_label")),
            anchor_label=cast(str | None, metadata.get("anchor_label")),
        )


@dataclass(frozen=True, slots=True)
class RagParentChunk:
    """父块表写入模型。

    父块保留较完整原文，用于回答时向主模型提供引用上下文，而不是用于检索。
    """

    chunk_id: str  # chunking engine 产出的稳定 chunk id
    text: str  # chunk 原文
    chunk_index: int  # 在所属文档内的顺序索引，从 0 开始
    start_offset: int | None = None  # 在整篇 Markdown 中的起始偏移
    end_offset: int | None = None  # 在整篇 Markdown 中的结束偏移
    extra_indexes: tuple[RagChunkExtraIndex, ...] = ()  # 命中的额外索引，可直接反查证据位置
    content_hash: str = ""  # 原文 hash，后续可用于版本一致性校验

    @classmethod
    def from_chunk(
            cls,
            chunk: Chunk,
            *,
            extra_indexes: tuple[RagChunkExtraIndex, ...] = (),
    ) -> "RagParentChunk":
        """把 chunking engine 的父块投影成父块表模型。"""
        return cls(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            extra_indexes=extra_indexes,
            content_hash=chunk.content_hash,
        )

    @property
    def page_label(self) -> str | None:
        return _page_label(self.extra_indexes)

    @property
    def section_path(self) -> tuple[str, ...]:
        return _section_path(self.extra_indexes)

    @property
    def anchor_labels(self) -> tuple[str, ...]:
        return _anchor_labels(self.extra_indexes)


@dataclass(frozen=True, slots=True)
class RagChildChunk:
    """子块表写入模型。

    子块是检索的基本单元；原始 text 用于最终引用展示，indexing_text 用于
    embedding 和 lexical indexing。两者必须分开，避免 indexing 信号污染引用原文。
    """

    chunk_id: str  # chunking engine 产出的稳定 chunk id
    text: str  # chunk 原文，最终回答引用时使用
    chunk_index: int  # 在所属文档内的顺序索引，从 0 开始
    parent_chunk_id: str  # 子块关联的父块 id，用于从子块反查完整父上下文
    start_offset: int | None = None  # 在整篇 Markdown 中的起始偏移
    end_offset: int | None = None  # 在整篇 Markdown 中的结束偏移
    extra_indexes: tuple[RagChunkExtraIndex, ...] = ()  # 命中的额外索引，可直接反查证据位置
    content_hash: str = ""  # 原文 hash，后续可用于版本一致性校验
    indexing_context: str = ""  # 小模型生成的上下文补充，随子块入库
    indexing_text: str = ""  # 面向 embedding / lexical indexing 的完整文本

    @classmethod
    def from_chunk(
            cls,
            chunk: Chunk,
            *,
            extra_indexes: tuple[RagChunkExtraIndex, ...] = (),
    ) -> "RagChildChunk":
        """把 chunking engine 的子块投影成子块表模型。"""
        return cls(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            parent_chunk_id=chunk.parent_chunk_id or "",
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            extra_indexes=extra_indexes,
            content_hash=chunk.content_hash,
        )

    def with_indexing_context(
            self,
            *,
            indexing_context: str,
            indexing_text: str,
    ) -> "RagChildChunk":
        """返回已补充 Context Indexing 结果的子块写入模型。"""
        return RagChildChunk(
            chunk_id=self.chunk_id,
            text=self.text,
            chunk_index=self.chunk_index,
            parent_chunk_id=self.parent_chunk_id,
            start_offset=self.start_offset,
            end_offset=self.end_offset,
            extra_indexes=self.extra_indexes,
            content_hash=self.content_hash,
            indexing_context=indexing_context,
            indexing_text=indexing_text,
        )

    @property
    def page_label(self) -> str | None:
        return _page_label(self.extra_indexes)

    @property
    def section_path(self) -> tuple[str, ...]:
        return _section_path(self.extra_indexes)

    @property
    def anchor_labels(self) -> tuple[str, ...]:
        return _anchor_labels(self.extra_indexes)


@dataclass(frozen=True, slots=True)
class RagChunkingResult:
    """RAG 分块结果，父子块分表写入。"""

    parent_chunks: tuple[RagParentChunk, ...]
    child_chunks: tuple[RagChildChunk, ...]
    pipeline: str
    resource_id: str = ""
    document_version: str = ""


@dataclass(frozen=True, slots=True)
class ContextIndexingInput:
    """单个 child chunk 的 Context Indexing 输入。"""

    parent_text: str  # child 所在父块全文，只用于补局部语义位置
    child_chunk: RagChildChunk  # 待补上下文的子块写入模型


@dataclass(frozen=True, slots=True)
class ContextIndexingResult:
    """Context Indexing 输出，用于后续 child chunk 入库。"""

    child_chunk: RagChildChunk  # 已带 indexing_context / indexing_text 的子块

    @property
    def evidence_text(self) -> str:
        return self.child_chunk.text

    @property
    def indexing_context(self) -> str:
        return self.child_chunk.indexing_context

    @property
    def indexing_text(self) -> str:
        return self.child_chunk.indexing_text


def _page_label(extra_indexes: tuple[RagChunkExtraIndex, ...]) -> str | None:
    """取 chunk 关联的第一个页码标签；多个 page 索引时以第一个为准。"""
    for extra_index in extra_indexes:
        if extra_index.index_kind != IndexKind.PAGE:
            continue
        if extra_index.page_label:
            return extra_index.page_label
    return None


def _section_path(extra_indexes: tuple[RagChunkExtraIndex, ...]) -> tuple[str, ...]:
    """取 chunk 关联的最深章节路径，用于展示引用位置。"""
    best_path: tuple[str, ...] = ()
    for extra_index in extra_indexes:
        if extra_index.index_kind != IndexKind.SECTION or not extra_index.section_path:
            continue
        if len(extra_index.section_path) > len(best_path):
            best_path = extra_index.section_path
    return best_path


def _anchor_labels(extra_indexes: tuple[RagChunkExtraIndex, ...]) -> tuple[str, ...]:
    """取 chunk 关联的所有锚点标签，保持顺序并去重。"""
    seen: dict[str, None] = {}
    for extra_index in extra_indexes:
        if extra_index.index_kind != IndexKind.ANCHOR or not extra_index.anchor_label:
            continue
        seen.setdefault(extra_index.anchor_label, None)
    return tuple(seen)
