"""constructor 内部使用的原文 span 渲染和映射规则。"""

from rag.utils.chunkers import SourceSpan


def _render_source_text(markdown: str, source_spans: list[SourceSpan]) -> str:
    return "\n\n".join(
        markdown[span.start_offset : span.end_offset] for span in source_spans
    )


def _map_rendered_spans_to_source(
    *,
    local_spans: list[SourceSpan],
    source_spans: list[SourceSpan],
) -> list[SourceSpan]:
    mapped: list[SourceSpan] = []
    rendered_cursor = 0

    for source_span in source_spans:
        source_length = source_span.end_offset - source_span.start_offset
        rendered_end = rendered_cursor + source_length
        for local_span in local_spans:
            if (
                local_span.start_offset >= rendered_end
                or local_span.end_offset <= rendered_cursor
            ):
                continue
            mapped_span = SourceSpan(
                source_span.start_offset
                + max(local_span.start_offset, rendered_cursor)
                - rendered_cursor,
                source_span.start_offset
                + min(local_span.end_offset, rendered_end)
                - rendered_cursor,
            )
            if mapped_span not in mapped:
                mapped.append(mapped_span)
        rendered_cursor = rendered_end + 2  # 与 source fragment 的双换行连接保持一致。

    return mapped


def _overlaps(target: SourceSpan, source_spans: list[SourceSpan]) -> bool:
    return any(
        span.start_offset < target.end_offset and span.end_offset > target.start_offset
        for span in source_spans
    )
