"""从文档结构构建稳定、可回源的 ReadingBlock。

ReadingBlock 是介于 Section 和 RetrivalChunk 之间的中等粒度文本单元：
- 每个 ReadingBlock 属于且仅属于一个 Section。
- 每个 ReadingBlock 持有原文 span 列表，可严格回源到权威 Markdown。
- ReadingBlock 内文本不超过 ``_READING_BLOCK_MAX_CHARACTERS``，便于下游抽取窗口复用。
"""

from collections.abc import Sequence
from hashlib import sha256

from rag.domain.models.structure import DocumentStructure, Section, StructureMode
from rag.domain.models.content import ReadingBlock
from rag.utils.chunkers import (
    BlockKind,
    ChunkDocument,
    MarkdownChunker,
    PlainTextChunker,
    PlainTextChunkerConfig,
    SourceSpan,
    TextBlock,
)
from rag.utils.chunkers.markdown import MarkdownParser

from ._source_spans import _map_rendered_spans_to_source, _overlaps, _render_source_text
from .structure import _build_section_id

# 单个 ReadingBlock 的最大字符数，与下游窗口抽取的最大上下文长度对齐。
_READING_BLOCK_MAX_CHARACTERS = 4000


def build_flat_text_sections(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
) -> list[Section]:
    """把无标题正文按 4000 个可见字符拆成无重叠导航 Section。

    用于 StructureMode.FLAT_TEXT 文档：原文没有可识别标题，无法用标题划分章节，
    因此按字符窗口把全文切成若干“全文片段” Section，每个 Section 自身即一个块边界，
    避免下游 ReadingBlock 跨越过长区间。
    """
    span_groups = _split_flat_text_source_spans(markdown)
    sections: list[Section] = []

    for index, source_spans in enumerate(span_groups):
        # own_span 取该组 span 的首尾并集，作为 Section 的“自身覆盖范围”。
        own_span = SourceSpan(
            source_spans[0].start_offset,
            source_spans[-1].end_offset,
        )
        title = f"全文片段 {index + 1}"
        sections.append(
            Section(
                section_id=_build_section_id(
                    resource_id=resource_id,
                    content_revision=content_revision,
                    kind="flat_text",
                    start_offset=own_span.start_offset,
                    end_offset=own_span.end_offset,
                ),
                title=title,
                level=1,
                parent_section_id=None,
                ordinal=index,
                section_path=[title],
                own_span=own_span,
                subtree_span=own_span,
            )
        )

    return sections


def build_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
) -> list[ReadingBlock]:
    """按结构模式生成 ReadingBlock；empty 文档不产生伪正文块。

    参数:
        structure: 已解析的文档结构，必须与 ``markdown`` 长度一致。
        sections: 与 structure 对应的 Section 列表；FLAT_TEXT 模式下应来自
            ``build_flat_text_sections``，SECTIONED 模式下来自 ``parse_document_structure``。

    返回:
        ReadingBlock 列表；函数会同时回填 ``section.preview``（取该 Section 下
        所有 block 的拼接文本前 500 字符），用于导航展示。
    """
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    # EMPTY 文档没有可索引正文，强制不产生 block，避免下游误用空内容。
    if structure.mode is StructureMode.EMPTY:
        if sections:
            raise ValueError("empty document must not contain sections")
        return []
    if structure.mode is StructureMode.FLAT_TEXT:
        blocks = _build_flat_text_reading_blocks(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
        )
    else:
        blocks = _build_section_reading_blocks(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
        )

    # 回填 section.preview：把该 Section 下所有 block 的原文拼接（替换换行）取前 500 字符。
    blocks_by_section: dict[str, list[ReadingBlock]] = {}
    for block in blocks:
        blocks_by_section.setdefault(block.section_id, []).append(block)
    for section in sections:
        section.preview = " ".join(
            block.raw_text for block in blocks_by_section.get(section.section_id, [])
        ).replace("\n", " ")[:500]
    return blocks


def _build_section_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
) -> list[ReadingBlock]:
    """SECTIONED 模式下按 Section 切分 ReadingBlock。

    每个 Section 的 own_span 文本送入 ``MarkdownChunker``，得到的 chunk 通过
    ``section.own_span.start_offset`` 偏移映射回原文坐标。Section 标题部分
    （heading_end 之前）会被跳过，避免把标题重复纳入正文块。
    """
    blocks: list[ReadingBlock] = []
    chunker = MarkdownChunker(max_characters=_READING_BLOCK_MAX_CHARACTERS)

    for section in sections:
        if section.own_span.end_offset > len(markdown):
            raise ValueError(f"section {section.section_id} exceeds markdown bounds")
        # 跳过空 Section（仅有标题、无正文内容）。
        if section.own_span.start_offset == section.own_span.end_offset:
            continue

        section_text = markdown[
            section.own_span.start_offset : section.own_span.end_offset
        ]
        result = chunker.chunk(
            document=ChunkDocument(
                text=section_text,
                document_id=section.section_id,
                content_type="text/markdown",
            )
        )
        # heading_end 是该 Section 标题（含其 markdown 行）在 section 局部坐标中的结束偏移；
        # 仅保留标题之后的正文 span，避免标题文字污染检索文本。
        heading_end = _heading_end_offset(result.blocks, section)
        ordinal = 0

        for chunk in result.chunks:
            # chunk.source_spans 是 section 局部坐标；转回 markdown 全局坐标，
            # 并过滤掉落在标题范围内的 span。
            source_spans = [
                SourceSpan(
                    section.own_span.start_offset + span.start_offset,
                    section.own_span.start_offset + span.end_offset,
                )
                for span in chunk.source_spans
                if span.end_offset > heading_end
            ]
            if not source_spans:
                continue
            blocks.append(
                _reading_block(
                    resource_id=resource_id,
                    content_revision=content_revision,
                    markdown=markdown,
                    section=section,
                    ordinal=ordinal,
                    source_spans=source_spans,
                    structure=structure,
                )
            )
            ordinal += 1

    return blocks


def _build_flat_text_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
) -> list[ReadingBlock]:
    """FLAT_TEXT 模式下生成 ReadingBlock。

    每个 Section 已经在 ``build_flat_text_sections`` 中按 4000 字符切好，
    这里直接基于同一组 span_groups 生成 ReadingBlock，并校验 Section ID 与 span 是否一致。
    """
    span_groups = _split_flat_text_source_spans(markdown)
    if len(sections) != len(span_groups):
        raise ValueError("flat text sections do not match reading block boundaries")

    blocks: list[ReadingBlock] = []
    for section, source_spans in zip(sections, span_groups, strict=True):
        # 重新计算 Section 期望 ID，确保它与 span 边界严格对应，防止传入的 Section 被篡改。
        expected_section_id = _build_section_id(
            resource_id=resource_id,
            content_revision=content_revision,
            kind="flat_text",
            start_offset=source_spans[0].start_offset,
            end_offset=source_spans[-1].end_offset,
        )
        if section.section_id != expected_section_id:
            raise ValueError(
                "flat text section identity does not match its source span"
            )
        blocks.append(
            _reading_block(
                resource_id=resource_id,
                content_revision=content_revision,
                markdown=markdown,
                section=section,
                ordinal=0,
                source_spans=source_spans,
                structure=structure,
            )
        )
    return blocks


def _split_flat_text_source_spans(markdown: str) -> list[list[SourceSpan]]:
    """把无标题 Markdown 切成多组 source span，每组对应一个 ReadingBlock 的覆盖区间。

    流程：
    1. 用 ``MarkdownParser`` 解析得到 block 列表，过滤掉页码标记和空 block，
       得到“有效内容 span”。
    2. 把这些 span 渲染为连续文本（``\\n\\n`` 拼接），交给 ``PlainTextChunker``
       按 4000 字符切分。
    3. chunker 产出的 local span 通过 ``_map_rendered_spans_to_source`` 映射回原文坐标，
       得到每个 ReadingBlock 真正的 source span 列表。
    """
    parsed_blocks = MarkdownParser().parse(markdown)
    effective_spans = [
        SourceSpan(block.start_offset, block.end_offset)
        for block in parsed_blocks
        if block.block_kind is not BlockKind.PAGE_MARKER
        and block.text.strip()
        and block.start_offset is not None
        and block.end_offset is not None
    ]
    if not effective_spans:
        return []

    rendered_text = _render_source_text(markdown, effective_spans)
    chunks = (
        PlainTextChunker(
            PlainTextChunkerConfig(
                chunk_size=_READING_BLOCK_MAX_CHARACTERS,
                chunk_overlap=0,
            )
        )
        .chunk(document=ChunkDocument(text=rendered_text))
        .chunks
    )

    return [
        _map_rendered_spans_to_source(
            local_spans=list(chunk.source_spans),
            source_spans=effective_spans,
        )
        for chunk in chunks
    ]


def _heading_end_offset(
    parsed_blocks: Sequence[TextBlock],
    section: Section,
) -> int:
    """计算 Section 标题在 section 局部坐标中的结束偏移。

    规则：
    - level == 0（根 Section）没有标题，返回 0（即不跳过任何文本）。
    - 其它 Section 必须以一个 HEADING block 开头，否则视为结构错误；
      返回该 heading block 的 ``end_offset`` 作为正文起点。
    """
    if section.level == 0:
        return 0
    first_block = parsed_blocks[0] if parsed_blocks else None
    if first_block is None or first_block.block_kind is not BlockKind.HEADING:
        raise ValueError(
            f"section {section.section_id} does not start with its heading"
        )
    if first_block.end_offset is None:
        raise ValueError(f"section {section.section_id} heading has no source offset")
    return first_block.end_offset


def _reading_block(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    section: Section,
    ordinal: int,
    source_spans: list[SourceSpan],
    structure: DocumentStructure,
) -> ReadingBlock:
    """组装单个 ``ReadingBlock`` 实例。

    page_labels / anchor_labels 通过 ``_overlaps`` 从结构中筛选与该 block span
    相交的页面/锚点，使 ReadingBlock 自带结构上下文，便于下游检索时直接定位。
    """
    return ReadingBlock(
        block_id=_build_reading_block_id(
            resource_id=resource_id,
            content_revision=content_revision,
            section_id=section.section_id,
            source_spans=source_spans,
        ),
        section_id=section.section_id,
        ordinal=ordinal,
        raw_text=_render_source_text(markdown, source_spans),
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


def _build_reading_block_id(
    *,
    resource_id: str,
    content_revision: str,
    section_id: str,
    source_spans: list[SourceSpan],
) -> str:
    """基于资源、revision、Section、span 边界生成稳定的 ReadingBlock ID。

    span_identity 形如 ``"start:end;start:end"``，确保 span 顺序与边界都参与哈希，
    避免不同 ReadingBlock 因前缀相同而冲突。
    """
    span_identity = ";".join(
        f"{span.start_offset}:{span.end_offset}" for span in source_spans
    )
    identity = f"{resource_id}\0{content_revision}\0{section_id}\0{span_identity}"
    return f"rsb_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
