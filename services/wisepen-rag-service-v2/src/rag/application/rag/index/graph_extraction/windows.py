"""从已发布 ReadingBlock 构建可精确回源的图抽取窗口。"""

from dataclasses import dataclass, field

from rag.domain.repositories.mongo.readers.graph_build_source import GraphBuildSource
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan
from rag.utils.xml_markup import xml_attr, xml_cdata

_ADJACENT_CONTEXT_CHARACTERS = 800
_WINDOW_CHARACTERS = 6_000
_WINDOW_OVERLAP_CHARACTERS = 2_400


@dataclass(slots=True)
class ExtractionSourceMapping:
    """抽取窗口字符区间到权威 Markdown 字符区间的映射。"""

    window_start: int
    window_end: int
    source_span: SourceSpan


@dataclass(slots=True)
class KnowledgeExtractionWindow:
    """一个 ReadingBlock 内可独立抽取并精确回源的窗口。"""

    resource_id: str
    content_revision: str
    reading_block_id: str
    section_path: list[str]
    window_id: str
    ordinal: int
    text: str
    source_mappings: list[ExtractionSourceMapping] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)
    previous_context: str = ""
    next_context: str = ""


def build_extraction_windows(
    source: GraphBuildSource,
) -> list[KnowledgeExtractionWindow]:
    """以 ReadingBlock 为归属边界构建窗口，邻接上下文不参与证据定位。"""
    sections_by_id = {section.section_id: section for section in source.sections}
    windows: list[KnowledgeExtractionWindow] = []

    for block_index, block in enumerate(source.reading_blocks):
        if not block.raw_text.strip() or not block.source_spans:
            continue
        section = sections_by_id.get(block.section_id)
        if section is None:
            raise ValueError(f"reading block {block.block_id} has no section")

        mappings = _source_mappings(source.markdown, block.raw_text, block.source_spans)
        source_refs = [
            source_ref
            for source_ref in source.source_refs
            if source_ref.reading_block_id == block.block_id
        ]
        if not source_refs:
            continue

        previous = source.reading_blocks[block_index - 1] if block_index else None
        next_block = (
            source.reading_blocks[block_index + 1]
            if block_index + 1 < len(source.reading_blocks)
            else None
        )
        for window_index, (start, end) in enumerate(
            _window_ranges(len(block.raw_text))
        ):
            whole_block = start == 0 and end == len(block.raw_text)
            windows.append(
                KnowledgeExtractionWindow(
                    resource_id=source.resource_id,
                    content_revision=source.content_revision,
                    reading_block_id=block.block_id,
                    section_path=list(section.section_path),
                    window_id=(
                        block.block_id
                        if whole_block
                        else f"{block.block_id}:window:{window_index}"
                    ),
                    ordinal=len(windows),
                    text=block.raw_text[start:end],
                    source_mappings=_clip_mappings(mappings, start, end),
                    source_refs=list(source_refs),
                    previous_context=(
                        previous.raw_text[-_ADJACENT_CONTEXT_CHARACTERS:]
                        if previous is not None
                        and previous.section_id == block.section_id
                        and start == 0
                        else ""
                    ),
                    next_context=(
                        next_block.raw_text[:_ADJACENT_CONTEXT_CHARACTERS]
                        if next_block is not None
                        and next_block.section_id == block.section_id
                        and end == len(block.raw_text)
                        else ""
                    ),
                )
            )
    return windows


def render_extraction_window(window: KnowledgeExtractionWindow) -> str:
    """渲染 GraphRAG 输入，并明确 evidence 只能来自当前窗口。"""
    section_path = " > ".join(window.section_path) or "(document root)"
    return f"""EXTRACTION_RULES:
- Extract only facts supported by <current_reading_block>.
- evidence_quote must be one exact continuous substring of <current_reading_block>.
- Previous and next context are only for disambiguation.
- Use the current Resource node and copy resource_id exactly.
- RELATED_TO requires a specific predicate.

<extraction_window resource_id="{xml_attr(window.resource_id)}">
  <section_path>{xml_cdata(section_path)}</section_path>
  <previous_context>{xml_cdata(window.previous_context)}</previous_context>
  <current_reading_block>{xml_cdata(window.text)}</current_reading_block>
  <next_context>{xml_cdata(window.next_context)}</next_context>
</extraction_window>
"""


def _source_mappings(
    markdown: str,
    raw_text: str,
    source_spans: list[SourceSpan],
) -> list[ExtractionSourceMapping]:
    mappings: list[ExtractionSourceMapping] = []
    cursor = 0
    for source_span in source_spans:
        source_text = markdown[source_span.start_offset : source_span.end_offset]
        local_start = raw_text.find(source_text, cursor)
        if not source_text or local_start < 0:
            raise ValueError("reading block source span does not match raw text")
        local_end = local_start + len(source_text)
        mappings.append(
            ExtractionSourceMapping(
                window_start=local_start,
                window_end=local_end,
                source_span=source_span,
            )
        )
        cursor = local_end
    return mappings


def _window_ranges(text_length: int) -> list[tuple[int, int]]:
    if text_length <= _WINDOW_CHARACTERS:
        return [(0, text_length)]

    ranges: list[tuple[int, int]] = []
    start = 0
    step = _WINDOW_CHARACTERS - _WINDOW_OVERLAP_CHARACTERS
    while start < text_length:
        end = min(start + _WINDOW_CHARACTERS, text_length)
        ranges.append((start, end))
        if end == text_length:
            break
        start += step
    return ranges


def _clip_mappings(
    mappings: list[ExtractionSourceMapping],
    window_start: int,
    window_end: int,
) -> list[ExtractionSourceMapping]:
    clipped: list[ExtractionSourceMapping] = []
    for mapping in mappings:
        start = max(mapping.window_start, window_start)
        end = min(mapping.window_end, window_end)
        if start >= end:
            continue
        source_start = (
            mapping.source_span.start_offset + start - mapping.window_start
        )
        clipped.append(
            ExtractionSourceMapping(
                window_start=start - window_start,
                window_end=end - window_start,
                source_span=SourceSpan(source_start, source_start + end - start),
            )
        )
    return clipped
