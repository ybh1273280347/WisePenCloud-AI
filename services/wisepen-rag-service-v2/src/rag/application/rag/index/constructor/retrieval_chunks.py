"""从 ReadingBlock 构建检索评分使用的 RetrievalChunk。

RetrievalChunk 是最细粒度的索引单元，主要用于向量检索：
- 每个 ReadingBlock 会被进一步切成多个 RetrievalChunk（默认 800 字符），
  使向量索引在更小范围内匹配，提升召回精度。
- FLAT_TEXT 模式下使用 ``PlainTextChunker`` 并允许 100 字符重叠，避免句子被切断；
  其它模式使用 ``MarkdownChunker`` 保留 markdown 结构边界。
- 每个 RetrievalChunk 持有自己的 source_spans（已映射回原文坐标），可独立回源。
"""

from hashlib import sha256

from rag.domain.models.structure import DocumentStructure, Section, StructureMode
from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk
from rag.utils.chunkers import (
    ChunkDocument,
    MarkdownChunker,
    PlainTextChunker,
    PlainTextChunkerConfig,
    SourceSpan,
)

from ._source_spans import _map_rendered_spans_to_source, _overlaps, _render_source_text
from .reading_blocks import _build_reading_block_id

# 单个 RetrievalChunk 的最大字符数，与下游向量模型的最佳输入长度对齐。
_RETRIEVAL_CHUNK_MAX_CHARACTERS = 800
# FLAT_TEXT 模式下相邻 chunk 之间的字符重叠量，避免句子边界被切断造成语义损失。
_FLAT_TEXT_CHUNK_OVERLAP = 100


def build_retrieval_chunks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
) -> list[RetrievalChunk]:
    """校验 ReadingBlock 后生成用于评分的确定性子块。

    流程：
    1. ``_validate_reading_blocks`` 严格校验 ReadingBlock 完整性（ID、归属、span 合法性、
       原文一致性），失败则抛错以保证索引数据可信。
    2. 按结构模式选择 chunker：FLAT_TEXT 用纯文本切分（带重叠），
       其它用 Markdown 切分（保留结构）。
    3. 对每个 ReadingBlock 切出若干 chunk，把 chunk 在渲染文本上的 local span
       映射回原文 source_spans，并附带 page_labels / anchor_labels 结构上下文。
    4. 最后校验所有 chunk_id 唯一。
    """
    sections_by_id = _validate_reading_blocks(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=sections,
        reading_blocks=reading_blocks,
    )
    # FLAT_TEXT 使用纯文本切分器并允许重叠；其它模式保留 markdown 结构边界。
    chunker = (
        PlainTextChunker(
            PlainTextChunkerConfig(
                chunk_size=_RETRIEVAL_CHUNK_MAX_CHARACTERS,
                chunk_overlap=_FLAT_TEXT_CHUNK_OVERLAP,
            )
        )
        if structure.mode is StructureMode.FLAT_TEXT
        else MarkdownChunker(max_characters=_RETRIEVAL_CHUNK_MAX_CHARACTERS)
    )
    chunks: list[RetrievalChunk] = []

    for reading_block in reading_blocks:
        section = sections_by_id[reading_block.section_id]
        result = chunker.chunk(
            document=ChunkDocument(
                text=reading_block.raw_text,
                document_id=reading_block.block_id,
                content_type=(
                    "text/plain"
                    if structure.mode is StructureMode.FLAT_TEXT
                    else "text/markdown"
                ),
            )
        )
        for chunk in result.chunks:
            # chunk.source_spans 是 ReadingBlock 渲染文本上的偏移（local 坐标），
            # 需要映射回原文坐标，使其可以独立回源。
            source_spans = _map_rendered_spans_to_source(
                local_spans=list(chunk.source_spans),
                source_spans=reading_block.source_spans,
            )
            if not source_spans:
                raise ValueError(
                    f"retrieval chunk from {reading_block.block_id} has no source span"
                )
            # raw_text 必须直接从原文渲染，确保与权威源完全一致，不可使用 chunker 给的文本。
            raw_text = _render_source_text(markdown, source_spans)
            chunks.append(
                RetrievalChunk(
                    chunk_id=_build_retrieval_chunk_id(
                        reading_block_id=reading_block.block_id,
                        source_spans=source_spans,
                    ),
                    reading_block_id=reading_block.block_id,
                    section_id=section.section_id,
                    section_path=list(section.section_path),
                    raw_text=raw_text,
                    index_text=raw_text,
                    source_spans=source_spans,
                    page_labels=[
                        page.page_label
                        for page in structure.pages
                        if _overlaps(page.source_span, source_spans)
                    ],
                    anchor_labels=[
                        anchor.label
                        for anchor in structure.anchors
                        if _overlaps(anchor.source_span, source_spans)
                    ],
                )
            )

    # chunk_id 唯一性兜底校验，避免不同 chunk 因哈希碰撞或逻辑错误被误判为相同。
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("retrieval chunk identities are not unique")
    return chunks


def _build_retrieval_chunk_id(
    *,
    reading_block_id: str,
    source_spans: list[SourceSpan],
) -> str:
    """基于 ReadingBlock 和 span 边界生成稳定的 RetrievalChunk ID。

    同一 ReadingBlock 下不同 chunk 的 source_spans 必然不同，因此 ID 不会冲突；
    span 顺序参与哈希保证映射确定性。
    """
    span_identity = ";".join(
        f"{span.start_offset}:{span.end_offset}" for span in source_spans
    )
    identity = f"{reading_block_id}\0{span_identity}"
    return f"rrc_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def _validate_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
) -> dict[str, Section]:
    """对传入的 ReadingBlock 执行严格一致性校验，返回 section_id -> Section 映射。

    校验项：
    - 结构总长度与 markdown 一致；section ID 唯一。
    - EMPTY 文档不应有 reading_blocks。
    - 每个 block 的 section_id 必须存在；source_spans 非空且不退化为空区间。
    - block 的 source_spans 必须落在其 section.own_span 范围内，且内部不互相重叠。
    - block.raw_text 必须与 ``_render_source_text`` 渲染结果一致（保证未被篡改）。
    - block.block_id 必须能根据其归属与 span 重新计算出来（防伪造身份）。
    - 同一 section 内 block.ordinal 必须是 0..N-1 连续整数。
    """
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    sections_by_id = {section.section_id: section for section in sections}
    if len(sections_by_id) != len(sections):
        raise ValueError("section identities are not unique")
    if structure.mode is StructureMode.EMPTY and reading_blocks:
        raise ValueError("empty document must not contain reading blocks")

    blocks_by_section: dict[str, list[ReadingBlock]] = {}
    seen_block_ids: set[str] = set()
    for block in reading_blocks:
        if block.block_id in seen_block_ids:
            raise ValueError("reading block identities are not unique")
        seen_block_ids.add(block.block_id)
        section = sections_by_id.get(block.section_id)
        
        if section is None:
            raise ValueError(f"reading block {block.block_id} has no section")
        if not block.source_spans:
            raise ValueError(f"reading block {block.block_id} has no source span")

        # 空区间（start == end）没有意义，会污染下游 chunker 输出。
        if any(span.start_offset == span.end_offset for span in block.source_spans):
            raise ValueError(f"reading block {block.block_id} has an empty source span")

        # block 的 span 必须完全落在其 Section 的 own_span 内。
        if any(
            span.start_offset < section.own_span.start_offset
            or span.end_offset > section.own_span.end_offset
            for span in block.source_spans
        ):
            raise ValueError(f"reading block {block.block_id} exceeds its section")

        # 同一 block 内 span 必须按顺序排列且不互相重叠（半开区间语义）。
        if any(
            left.end_offset > right.start_offset
            for left, right in zip(
                block.source_spans,
                block.source_spans[1:],
                strict=False,
            )
        ):
            raise ValueError(f"reading block {block.block_id} has overlapping spans")

        # raw_text 必须能从权威 markdown 重新渲染出来，保证未被外部修改。
        if block.raw_text != _render_source_text(markdown, block.source_spans):
            raise ValueError(
                f"reading block {block.block_id} does not match authoritative source"
            )

        # 重新计算 block_id 并比对，确保 block 的身份与其归属严格对应。
        expected_block_id = _build_reading_block_id(
            resource_id=resource_id,
            content_revision=content_revision,
            section_id=section.section_id,
            source_spans=block.source_spans,
        )
        if block.block_id != expected_block_id:
            raise ValueError("reading block identity does not match its ownership")
        blocks_by_section.setdefault(section.section_id, []).append(block)

    # 同一 Section 内 ordinal 必须是 0..N-1 的连续整数，保证下游可按 ordinal 排序还原顺序。
    for section_id, section_blocks in blocks_by_section.items():
        if [block.ordinal for block in section_blocks] != list(
            range(len(section_blocks))
        ):
            raise ValueError(f"section {section_id} has invalid reading block ordinals")

    return sections_by_id
