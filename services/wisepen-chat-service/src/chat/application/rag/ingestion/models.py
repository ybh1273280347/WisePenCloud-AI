from __future__ import annotations

from dataclasses import dataclass, field

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
    child_text: str  # 最终要进入长期索引的原始子块正文
    document_title: str = ""  # 文档标题，帮助术语消歧
    section_path: tuple[str, ...] = ()  # 章节路径，帮助模型判断局部语义角色


@dataclass(frozen=True, slots=True)
class ContextIndexingResult:
    """Context Indexing 输出，用于后续 embedding / lexical / graph extraction。"""

    evidence_text: str  # 保留原始 child_text，供最终引用与展示
    indexing_text: str  # 面向检索与消歧的补全文本
    context_summary: str = ""  # 模型生成的局部语义摘要
    important_terms: tuple[str, ...] = ()  # 从文档上下文中抽出的稳定术语
    usage_tokens: int = 0  # 本次小模型调用的 token 用量
    metadata: dict[str, object] = field(default_factory=dict)  # 调试与策略标记
