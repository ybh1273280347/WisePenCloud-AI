"""构建 RetrievalChunk 到权威原文的 SourceRef。

SourceRef 是检索结果到原文的“回源凭据”：它把 RetrievalChunk、ReadingBlock、Section
与权威 markdown 的 source_spans 固化为一条不可篡改的归属链。检索命中后可通过 SourceRef
直接定位到原文位置、所属章节、所属页面与锚点，无需回查 chunk 本身。
"""

from hashlib import sha256

from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk, SourceRef
from rag.domain.models.structure import DocumentStructure, Section

from ._source_spans import _overlaps, _render_source_text
from .retrieval_chunks import _build_retrieval_chunk_id


def build_source_refs(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
    retrieval_chunks: list[RetrievalChunk],
) -> list[SourceRef]:
    """固化 chunk、ReadingBlock、Section 与权威原文的完整归属链。

    对每个 RetrievalChunk 执行严格一致性校验后，生成一条 ``SourceRef``：
    - chunk 必须存在 source_spans 且无空区间。
    - chunk 必须归属一个 ReadingBlock，且该 block 必须归属一个 Section。
    - chunk.section_path 必须与 Section 自身的 section_path 一致。
    - chunk.source_spans 必须完全落在 ReadingBlock.source_spans 范围内。
    - chunk.raw_text 必须能从原文重新渲染（防篡改）。
    - chunk.page_labels / anchor_labels 必须与结构计算结果一致。
    - chunk.chunk_id 必须能由 ReadingBlock 与 span 重新算出（防伪造身份）。
    """
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    sections_by_id = {section.section_id: section for section in sections}
    if len(sections_by_id) != len(sections):
        raise ValueError("section identities are not unique")
    blocks_by_id = {block.block_id: block for block in reading_blocks}
    if len(blocks_by_id) != len(reading_blocks):
        raise ValueError("reading block identities are not unique")

    refs: list[SourceRef] = []
    for chunk in retrieval_chunks:
        if not chunk.source_spans:
            raise ValueError(f"retrieval chunk {chunk.chunk_id} has no source span")
        # 空区间没有回源意义，且会污染 span 序列化。
        if any(span.start_offset == span.end_offset for span in chunk.source_spans):
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has an empty source span"
            )
        block = blocks_by_id.get(chunk.reading_block_id)
        if block is None:
            raise ValueError(f"retrieval chunk {chunk.chunk_id} has no reading block")
        section = sections_by_id.get(chunk.section_id)
        # block 与 chunk 必须指向同一个 Section，避免跨 Section 错挂。
        if section is None or block.section_id != section.section_id:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has an invalid section owner"
            )
        if chunk.section_path != section.section_path:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has an invalid section path"
            )
        # chunk 的每个 span 必须完全落在 block 的某个 span 内（不允许跨 block 边界）。
        if any(
            not any(
                block_span.start_offset <= chunk_span.start_offset
                and chunk_span.end_offset <= block_span.end_offset
                for block_span in block.source_spans
            )
            for chunk_span in chunk.source_spans
        ):
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} exceeds its reading block"
            )
        # raw_text 必须能从权威 markdown 重新渲染，保证未被外部修改。
        if chunk.raw_text != _render_source_text(markdown, chunk.source_spans):
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} does not match authoritative source"
            )
        # 重新计算期望的 page_labels，确保 chunk 自带的页面标签与结构一致。
        expected_page_labels = [
            page.page_label
            for page in structure.pages
            if _overlaps(page.source_span, chunk.source_spans)
        ]
        if chunk.page_labels != expected_page_labels:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has invalid page labels"
            )
        # 同上，校验 anchor_labels。
        expected_anchor_labels = [
            anchor.label
            for anchor in structure.anchors
            if _overlaps(anchor.source_span, chunk.source_spans)
        ]
        if chunk.anchor_labels != expected_anchor_labels:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has invalid anchor labels"
            )
        # 重新计算 chunk_id 并比对，确保 chunk 身份与其归属严格对应，防伪造。
        expected_chunk_id = _build_retrieval_chunk_id(
            reading_block_id=block.block_id,
            source_spans=chunk.source_spans,
        )
        if chunk.chunk_id != expected_chunk_id:
            raise ValueError("retrieval chunk identity does not match its ownership")

        refs.append(
            SourceRef(
                ref_id=_build_source_ref_id(
                    resource_id=resource_id,
                    content_revision=content_revision,
                    chunk=chunk,
                ),
                resource_id=resource_id,
                content_revision=content_revision,
                chunk_id=chunk.chunk_id,
                reading_block_id=block.block_id,
                section_id=section.section_id,
                section_path=list(section.section_path),
                source_spans=list(chunk.source_spans),
                page_labels=list(chunk.page_labels),
                anchor_labels=list(chunk.anchor_labels),
            )
        )

    # ref_id 唯一性兜底校验，避免不同 chunk 因哈希碰撞或逻辑错误被误判为相同。
    if len({ref.ref_id for ref in refs}) != len(refs):
        raise ValueError("source ref identities are not unique")
    return refs


def _build_source_ref_id(
    *,
    resource_id: str,
    content_revision: str,
    chunk: RetrievalChunk,
) -> str:
    """基于资源、revision、chunk、block、section 五元组生成稳定 SourceRef ID。

    五元组共同决定身份，保证同一 chunk 在同一 revision 下生成的 SourceRef 永远一致，
    任何一项变化都会让 ref_id 改变，从而触发下游重建。
    """
    identity = (
        f"{resource_id}\0{content_revision}\0{chunk.chunk_id}"
        f"\0{chunk.reading_block_id}\0{chunk.section_id}"
    )
    return f"rsrc_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
