from __future__ import annotations

from dataclasses import dataclass

from chat.application.utils.chunking_engine.models import Chunk


@dataclass(frozen=True, slots=True)
class RagParentChunk:
    """父块表写入模型。"""

    chunk_id: str  # chunking engine 产出的稳定 chunk id
    text: str  # chunk 原文
    chunk_index: int  # 在所属文档内的顺序索引
    section_path: tuple[str, ...] = ()  # 结构化章节路径
    anchor_names: tuple[str, ...] = ()  # Markdown 锚点信息
    page: int | None = None  # 文档页码，适用于 parse 阶段已注入页码的内容
    content_hash: str = ""  # 原文 hash，后续可用于版本一致性校验

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> "RagParentChunk":
        """把 chunking engine 的父块投影成父块表模型。"""
        metadata = chunk.metadata
        return cls(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            section_path=tuple(metadata.get("section_paths", ())),
            anchor_names=tuple(metadata.get("anchor_names", ())),
            page=metadata.get("page"),
            content_hash=chunk.content_hash,
        )


@dataclass(frozen=True, slots=True)
class RagChildChunk:
    """子块表写入模型。"""

    chunk_id: str  # chunking engine 产出的稳定 chunk id
    text: str  # chunk 原文
    chunk_index: int  # 在所属文档内的顺序索引
    parent_chunk_id: str  # 子块关联的父块 id
    section_path: tuple[str, ...] = ()  # 结构化章节路径
    anchor_names: tuple[str, ...] = ()  # Markdown 锚点信息
    page: int | None = None  # 文档页码，适用于 parse 阶段已注入页码的内容
    content_hash: str = ""  # 原文 hash，后续可用于版本一致性校验
    indexing_context: str = ""  # 小模型生成的上下文补充，随子块入库
    indexing_text: str = ""  # 面向 embedding / lexical indexing 的完整文本

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> "RagChildChunk":
        """把 chunking engine 的子块投影成子块表模型。"""
        metadata = chunk.metadata
        return cls(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            parent_chunk_id=chunk.parent_chunk_id or "",
            section_path=tuple(metadata.get("section_paths", ())),
            anchor_names=tuple(metadata.get("anchor_names", ())),
            page=metadata.get("page"),
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
            section_path=self.section_path,
            anchor_names=self.anchor_names,
            page=self.page,
            content_hash=self.content_hash,
            indexing_context=indexing_context,
            indexing_text=indexing_text,
        )


@dataclass(frozen=True, slots=True)
class RagChunkingResult:
    """RAG 分块结果，父子块分表写入。"""

    parent_chunks: tuple[RagParentChunk, ...]
    child_chunks: tuple[RagChildChunk, ...]
    pipeline: str


@dataclass(frozen=True, slots=True)
class ContextIndexingInput:
    """单个 child chunk 的 Context Indexing 输入。"""

    parent_text: str  # child 所在父块全文，只用于补局部语义位置
    child_chunk: RagChildChunk  # 待补上下文的子块写入模型
    document_title: str = ""  # 文档标题，帮助判断子块局部语义位置


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
