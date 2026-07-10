from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_PAGE_MARKER_PREFIX = "<!-- page "
_AUXILIARY_BLOCK_TYPES = frozenset({
    "header",
    "footer",
    "page_number",
    "aside_text",
    "page_footnote",
})
_ANCHOR_FIELDS = (
    "text",
    "img_path",
    "content",
    "image_caption",
    "image_footnote",
    "table_caption",
    "table_body",
    "table_footnote",
    "code_caption",
    "code_body",
    "code_footnote",
    "list_items",
)


def insert_page_markers(
        markdown: str,
        content_list: object,
) -> str:
    """用 MinerU content list 为 Markdown 插入页码注释。

    只有每页首个非空正文块都能在 Markdown 中唯一且顺序定位时才修改；
    任一页无法可靠定位就返回原文，避免产生部分或猜测页码。
    """
    if _PAGE_MARKER_PREFIX in markdown or not isinstance(content_list, list):
        return markdown

    page_blocks: dict[int, list[Mapping[str, Any]]] = {}
    for item in content_list:
        if not isinstance(item, Mapping):
            return markdown

        page_idx = item.get("page_idx")
        if type(page_idx) is not int or page_idx < 0:
            return markdown
        if item.get("type") in _AUXILIARY_BLOCK_TYPES:
            continue

        page_blocks.setdefault(page_idx, []).append(item)

    marker_positions: list[tuple[int, int]] = []
    previous_position = -1
    for page_idx, blocks in sorted(page_blocks.items()):
        anchors = next(
            (anchors for block in blocks if (anchors := tuple(_block_anchors(block)))),
            None,
        )
        if anchors is None:
            return markdown

        anchor_positions = [
            position
            for anchor in anchors
            if (position := _unique_position(markdown, anchor)) is not None
        ]
        if not anchor_positions:
            return markdown

        block_position = _markdown_block_start(markdown, min(anchor_positions))
        if block_position <= previous_position:
            return markdown

        marker_positions.append((block_position, page_idx + 1))
        previous_position = block_position

    if not marker_positions:
        return markdown

    annotated = markdown
    for position, page_number in reversed(marker_positions):
        annotated = (
            annotated[:position]
            + f"<!-- page {page_number} -->\n\n"
            + annotated[position:]
        )
    return annotated


def _block_anchors(block: Mapping[str, Any]) -> Iterable[str]:
    seen: set[str] = set()
    for field in _ANCHOR_FIELDS:
        value = block.get(field)
        values = value if isinstance(value, list) else (value,)
        for item in values:
            if not isinstance(item, str):
                continue
            anchor = item.strip()
            if anchor and anchor not in seen:
                seen.add(anchor)
                yield anchor


def _unique_position(markdown: str, anchor: str) -> int | None:
    position = markdown.find(anchor)
    if position < 0:
        return None
    if markdown.find(anchor, position + len(anchor)) >= 0:
        return None
    return position


def _markdown_block_start(markdown: str, anchor_position: int) -> int:
    separator_position = markdown.rfind("\n\n", 0, anchor_position)
    return separator_position + 2 if separator_position >= 0 else 0
