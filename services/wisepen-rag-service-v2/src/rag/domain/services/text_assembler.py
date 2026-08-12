"""按 SourcePart 还原权威原文并校验连续覆盖关系。"""

from collections.abc import Sequence

from rag.domain.content_revision import SourcePart
from rag.utils.chunkers import SourceSpan


def assemble_source_text(
    parts: Sequence[SourcePart],
    source_spans: Sequence[SourceSpan],
) -> str:
    """拼接 source spans；分片缺失、重叠或文本长度错误时直接失败。"""
    if not source_spans:
        return ""
    ordered_parts = sorted(parts, key=lambda part: part.source_span.start_offset)
    revision = ordered_parts[0].content_revision if ordered_parts else "unknown"
    _validate_parts(ordered_parts, revision)

    fragments: list[str] = []
    for span in source_spans:
        cursor = span.start_offset
        span_fragments: list[str] = []
        for part in ordered_parts:
            part_start = part.source_span.start_offset
            part_end = part.source_span.end_offset
            if part_end <= cursor:
                continue
            if part_start >= span.end_offset:
                break
            if part_start > cursor:
                raise RuntimeError(
                    f"content revision {revision} source parts have a gap"
                )

            fragment_end = min(part_end, span.end_offset)
            span_fragments.append(
                part.text[cursor - part_start : fragment_end - part_start]
            )
            cursor = fragment_end
            if cursor == span.end_offset:
                break
        if cursor != span.end_offset:
            raise RuntimeError(
                f"content revision {revision} source parts do not cover span"
            )
        fragments.append("".join(span_fragments))
    return "\n\n".join(fragments)


def _validate_parts(parts: Sequence[SourcePart], content_revision: str) -> None:
    previous_end = None
    for part in parts:
        start = part.source_span.start_offset
        end = part.source_span.end_offset
        if end - start != len(part.text):
            raise RuntimeError(
                f"content revision {content_revision} has an invalid source part"
            )
        if previous_end is not None and start < previous_end:
            raise RuntimeError(
                f"content revision {content_revision} source parts overlap"
            )
        previous_end = end
