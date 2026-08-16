"""从 ReadingBlock 构建检索评分使用的 RetrievalChunk。

RetrievalChunk 是最细粒度的索引单元，主要用于向量检索：
- 每个 ReadingBlock 会被进一步切成多个 RetrievalChunk（默认 800 字符），
  使向量索引在更小范围内匹配，提升召回精度。
"""

from hashlib import sha256

from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk
from rag.domain.models.structure import DocumentStructure, Section
from rag.utils.chunkers import ChunkDocument, MarkdownChunker, SourceSpan

from ._source_spans import _map_rendered_spans_to_source, _overlaps, _render_source_text

# 单个 RetrievalChunk 的最大字符数，与下游向量模型的最佳输入长度对齐。
_RETRIEVAL_CHUNK_MAX_CHARACTERS = 800
# 相邻 chunk 之间的字符重叠量，缓解超长 block 硬切割造成的语义损失。
_RETRIEVAL_CHUNK_OVERLAP = 100


def build_retrieval_chunks(
    *,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
) -> list[RetrievalChunk]:
    """从上游刚构造的 ReadingBlock 生成用于评分的确定性子块。

    输入永远是 markdown（FLAT_TEXT 只是"无标题结构"，并非纯文本），统一用
    MarkdownChunker 切分（800 字符、100 重叠）；chunk 在渲染文本上的 rendered span
    映射回原文 source_spans，并附带 page_labels / anchor_labels 结构上下文。
    """
    sections_by_id = {section.section_id: section for section in sections}

    chunker = MarkdownChunker(
        max_characters=_RETRIEVAL_CHUNK_MAX_CHARACTERS,
        chunk_overlap=_RETRIEVAL_CHUNK_OVERLAP,
    )
    chunks: list[RetrievalChunk] = []

    for reading_block in reading_blocks:
        section = sections_by_id[reading_block.section_id]
        result = chunker.chunk(
            document=ChunkDocument(
                text=reading_block.raw_text,
                document_id=reading_block.block_id,
                content_type="text/markdown",
            )
        )
        for chunk in result.chunks:
            # chunk.source_spans 是 ReadingBlock 渲染文本上的偏移（rendered 坐标），
            # 需要映射回原文坐标，使其可以独立回源。
            source_spans = _map_rendered_spans_to_source(
                rendered_spans=list(chunk.source_spans),
                source_spans=reading_block.source_spans,
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

    return chunks


def _build_retrieval_chunk_id(
    *,
    reading_block_id: str,
    source_spans: list[SourceSpan],
) -> str:
    """基于 ReadingBlock 和 span 边界生成稳定的 RetrievalChunk ID。"""
    span_identity = ";".join(
        f"{span.start_offset}:{span.end_offset}" for span in source_spans
    )
    identity = f"{reading_block_id}\0{span_identity}"
    return f"rrc_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"

