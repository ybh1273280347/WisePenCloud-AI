"""LOCATE 与 Graph EXPAND 共享的模型可读检索视图。"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from rag.domain.models.graph import (
    KnowledgeEntityType,
    KnowledgeNode,
    KnowledgeNodeKind,
)
from rag.domain.models.provenance import SourceEvidence


@dataclass(slots=True)
class MatchRangeView:
    """相对于 ``RetrievalReadingBlockView.text`` 的 Python 字符半开区间。"""

    start_offset: int
    end_offset: int


@dataclass(slots=True)
class RetrievalMatchView:
    """触发 ReadingBlock 提升的检索 chunk 锚点，不重复返回 chunk 文本。"""

    chunk_id: str
    source_ref_id: str
    ranges: list[MatchRangeView] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalReadingBlockView:
    """检索命中后提升出的完整 ReadingBlock 正文及紧凑页范围。"""

    reading_block_id: str
    text: str
    page_range: str | None = None
    anchor_labels: list[str] = field(default_factory=list)
    matches: list[RetrievalMatchView] = field(default_factory=list)


@dataclass(slots=True)
class RetrievedSectionView:
    """承载命中 ReadingBlock；flat text 使用 synthetic Section 作为读取锚点。"""

    resource_id: str
    section_id: str
    title: str
    section_path: str
    reading_blocks: list[RetrievalReadingBlockView] = field(default_factory=list)


@dataclass(slots=True)
class KnowledgeNodeView:
    """用于后续图导航的紧凑节点锚点。"""

    node_id: str
    label: str
    kind: KnowledgeNodeKind
    entity_type: KnowledgeEntityType | None = None


def to_knowledge_node_view(node: KnowledgeNode) -> KnowledgeNodeView:
    return KnowledgeNodeView(
        node_id=node.node_id,
        label=node.label,
        kind=node.kind,
        entity_type=node.entity_type,
    )


def build_retrieved_section_views(
    records: list[SourceEvidence],
) -> list[RetrievedSectionView]:
    """按首次命中顺序把核验证据提升并归组为完整 ReadingBlock。"""
    sections: dict[tuple[str, str], RetrievedSectionView] = {}
    blocks: dict[tuple[str, str], RetrievalReadingBlockView] = {}

    for record in records:
        section_key = (record.source_ref.resource_id, record.section.section_id)
        section_view = sections.setdefault(
            section_key,
            RetrievedSectionView(
                resource_id=record.source_ref.resource_id,
                section_id=record.section.section_id,
                title=record.section.title,
                section_path=" > ".join(record.section.section_path),
            ),
        )
        block_key = (record.source_ref.resource_id, record.reading_block.block_id)
        block_view = blocks.get(block_key)
        if block_view is None:
            block_view = RetrievalReadingBlockView(
                reading_block_id=record.reading_block.block_id,
                text=record.reading_block.raw_text,
                page_range=_format_page_range(record.reading_block.page_labels),
                anchor_labels=list(record.reading_block.anchor_labels),
            )
            blocks[block_key] = block_view
            section_view.reading_blocks.append(block_view)
        block_view.matches.append(
            RetrievalMatchView(
                chunk_id=record.source_ref.chunk_id,
                source_ref_id=record.source_ref.ref_id,
                ranges=_relative_match_ranges(record),
            )
        )

    return list(sections.values())


def _format_page_range(page_labels: Sequence[str]) -> str | None:
    """把内部有序 page labels 投影为统一的模型可见页范围。"""
    labels = list(dict.fromkeys(page_labels))
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]} - {labels[-1]}"


def _relative_match_ranges(record: SourceEvidence) -> list[MatchRangeView]:
    """把权威 source spans 映射到 ReadingBlock 拼接文本的相对字符坐标。"""
    ranges: list[MatchRangeView] = []
    block_offset = 0
    for index, block_span in enumerate(record.reading_block.source_spans):
        for match_span in record.source_ref.source_spans:
            start = max(block_span.start_offset, match_span.start_offset)
            end = min(block_span.end_offset, match_span.end_offset)
            if start < end:
                ranges.append(
                    MatchRangeView(
                        start_offset=block_offset + start - block_span.start_offset,
                        end_offset=block_offset + end - block_span.start_offset,
                    )
                )
        block_offset += block_span.end_offset - block_span.start_offset
        if index + 1 < len(record.reading_block.source_spans):
            block_offset += 2
    if not ranges:
        raise ValueError(
            f"source ref {record.source_ref.ref_id} is outside its ReadingBlock"
        )
    return ranges
