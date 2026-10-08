"""工具正文的纯函数 Store 边界。

本模块只负责文本校验、分块和 receipt 组装；Redis client、key 和 TTL 由
``RedisToolContentRepository`` 自己声明，调用方不需要注入任何缓存对象。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

from common.utils.markdown import (
    Anchor,
    MarkdownChunker,
    MarkdownChunkerConfig,
    Section,
    SourceSpan,
    TokenCounter,
    default_token_counter,
)

_DEFAULT_MAX_CHARS = 20_000_000
_CACHE_CHUNKER_CONFIG = MarkdownChunkerConfig(
    target_chunk_tokens=800,
    split_threshold_tokens=1600,
)


@lru_cache(maxsize=1)
def _repository():
    """惰性创建 Redis 仓储，避免业务层持有依赖。"""

    from chat.core.persistence.redis.tool_content_repository import (
        RedisToolContentRepository,
    )

    return RedisToolContentRepository()


@dataclass(frozen=True, slots=True)
class ToolContentChunk:
    """缓存索引保存已切好的正文 chunk、原文边界和结构身份。"""

    text: str
    chunk_index: int
    start_offset: int
    end_offset: int
    source_spans: tuple[SourceSpan, ...]
    # 有真实 Section 时，一个 chunk 只对应一个 Section；flat 文本保持为空。
    section_id: str | None = None
    anchor_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StoredToolContent:
    """一个会话内可检索、可按结构确定性读取的完整工具正文。"""

    content_id: str
    session_id: str
    text: str
    chunks: tuple[ToolContentChunk, ...] = ()
    sections: tuple[Section, ...] = ()
    anchors: tuple[Anchor, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolContentReceipt:
    content_id: str
    chunk_count: int
    total_length: int


async def put_tool_content(
    *,
    session_id: str,
    text: str,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> ToolContentReceipt | None:
    """分块并持久化正文；空白或超限正文不进入 Redis。"""

    if max_chars < 1:
        raise ValueError("max_chars must be greater than 0")
    if not text or text.isspace() or len(text) > max_chars:
        return None

    # 缓存索引使用小子块提升命中精度；Chat 的原文 offset 在 adapter 层单独投影。
    token_counter = default_token_counter()
    result = MarkdownChunker(_CACHE_CHUNKER_CONFIG, token_counter=token_counter).chunk(
        text
    )
    stored = StoredToolContent(
        content_id=f"cnt_{uuid.uuid4().hex[:16]}",
        session_id=session_id,
        text=text,
        chunks=_build_cache_chunks(
            text, result.sections, result.anchors, token_counter
        ),
        sections=result.sections,
        anchors=result.anchors,
    )
    await _repository().put(stored)
    return ToolContentReceipt(
        content_id=stored.content_id,
        chunk_count=len(stored.chunks),
        total_length=len(text),
    )


def _build_cache_chunks(
    text: str,
    sections: tuple[Section, ...],
    anchors: tuple[Anchor, ...],
    counter: TokenCounter,
) -> tuple[ToolContentChunk, ...]:
    """Chat 独立构建原文范围索引，范围和检索正文始终指向同一文本。

    Common 的结构片段可能经过 normalization 或重复 header。它们不能
    反推字符位置，因此 Chat 在真实 section 原文上做保留所有字符的切分。
    """
    ranges = (
        [(section.own_span, section.section_id) for section in sections]
        if sections
        else [(SourceSpan(0, len(text)), None)]
    )
    # Parser 可以忽略前置 HTML/comment；缓存公开的是完整正文，不能丢掉它。
    if ranges and ranges[0][0].start_offset > 0:
        ranges.insert(0, (SourceSpan(0, ranges[0][0].start_offset), None))
    chunks: list[ToolContentChunk] = []
    for source_span, section_id in ranges:
        source_text = text[source_span.start_offset : source_span.end_offset]
        parts = (
            counter.split(source_text, _CACHE_CHUNKER_CONFIG.target_chunk_tokens)
            if counter.count(source_text) > _CACHE_CHUNKER_CONFIG.split_threshold_tokens
            else (source_text,)
        )
        cursor = source_span.start_offset
        for part in parts:
            span = SourceSpan(cursor, cursor + len(part))
            if part:
                chunks.append(
                    ToolContentChunk(
                        text=part,
                        chunk_index=len(chunks),
                        start_offset=span.start_offset,
                        end_offset=span.end_offset,
                        source_spans=(span,),
                        section_id=section_id,
                        anchor_labels=tuple(
                            anchor.label
                            for anchor in anchors
                            if anchor.source_span.start_offset < span.end_offset
                            and anchor.source_span.end_offset > span.start_offset
                        ),
                    )
                )
            cursor = span.end_offset
    return tuple(chunks)


async def get_tool_content(
    *,
    content_id: str,
    session_id: str,
) -> StoredToolContent | None:
    """读取正文并强制执行会话归属校验。"""

    stored = await _repository().get(content_id)
    if stored is None or stored.session_id != session_id:
        return None
    return stored
