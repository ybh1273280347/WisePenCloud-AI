from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin

from .plugins import standalone_figure_plugin


class NodeKind(StrEnum):
    """Markdown 语法树中会影响分块边界的结构类型。"""

    DOCUMENT = "document"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LIST_ITEM = "list_item"
    QUOTE = "quote"
    TABLE = "table"
    TABLE_HEADER = "table_header"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    CODE = "code"
    FORMULA = "formula"
    FIGURE = "figure"
    INLINE = "inline"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """原文中的 Python 字符半开区间。"""

    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise ValueError("source span must satisfy 0 <= start_offset <= end_offset")

    @property
    def length(self) -> int:
        return self.end_offset - self.start_offset


@dataclass(frozen=True, slots=True)
class DocumentNode:
    """解析器输出的结构事实；source_spans 是可选 provenance。"""

    node_id: str
    kind: NodeKind
    text: str
    source_spans: tuple[SourceSpan, ...] = ()
    children: tuple[DocumentNode, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def source_node_ids(self) -> tuple[str, ...]:
        """原始结构归属；派生片段可重复归属同一原始 Node，不代表精确文本覆盖。"""
        identities = self.metadata.get("source_node_ids")
        if identities is not None:
            return tuple(identities)
        return (
            self.node_id,
            *(
                identity
                for child in self.children
                for identity in child.source_node_ids
            ),
        )

    @property
    def start(self) -> int | None:
        return min((span.start_offset for span in self.source_spans), default=None)

    @property
    def end(self) -> int | None:
        return max((span.end_offset for span in self.source_spans), default=None)

NUMBERED_LABEL_RE = re.compile(
    r"^(?:[·•]\s*|[-*+]\s+)?[*_~\s]*"
    r"(?:(?P<table_label>Table|表格|表)|(?P<figure_label>Figure|Fig\.?|图))"
    r"\s*(?P<number>\d+(?:\.\d+)*)\s*[-:：.．、]\s*"
    r"(?P<title>\S(?:.*\S)?)[*_~\s]*$",
    re.IGNORECASE | re.DOTALL,
)
FORMULA_LABEL_RE = re.compile(
    r"(?:Equation|Eq\.?|公式)\s+\(?(?P<number>\d+(?:\.\d+)*)\)?",
    re.IGNORECASE,
)

_OPEN_KINDS: dict[str, NodeKind | None] = {
    "heading_open": NodeKind.SECTION,
    "paragraph_open": NodeKind.PARAGRAPH,
    "blockquote_open": NodeKind.QUOTE,
    "bullet_list_open": NodeKind.LIST,
    "ordered_list_open": NodeKind.LIST,
    "list_item_open": NodeKind.LIST_ITEM,
    "table_open": NodeKind.TABLE,
    "thead_open": NodeKind.TABLE_HEADER,
    "tbody_open": None,
    "tr_open": NodeKind.TABLE_ROW,
    "th_open": NodeKind.TABLE_CELL,
    "td_open": NodeKind.TABLE_CELL,
    "figure_open": NodeKind.FIGURE,
}


class DocumentParser:
    """将 markdown-it token tree 投影为保留嵌套结构和来源范围的 Node 树。"""

    def __init__(self) -> None:
        self._parser = (
            MarkdownIt("commonmark")
            .disable("lheading")
            .enable("table")
            .use(standalone_figure_plugin)
            .use(dollarmath_plugin)
        )

    def parse(self, text: str) -> tuple[DocumentNode, ...]:
        if not text:
            return ()

        line_offsets = _markdown_line_offsets(text)
        nodes = _TokenTreeBuilder(
            tokens=self._parser.parse(text),
            text=text,
            line_offsets=line_offsets,
        ).build()
        nodes = _normalize_nodes(nodes, text)
        if nodes:
            return tuple(
                _assign_structural_ids(node, f"node-{index}")
                for index, node in enumerate(nodes)
            )

        if text.strip():
            return (
                DocumentNode(
                    node_id="node-0",
                    kind=NodeKind.PARAGRAPH,
                    text=text,
                    source_spans=(SourceSpan(0, len(text)),),
                    metadata={"source_format": "raw"},
                ),
            )
        return ()


def _assign_structural_ids(node: DocumentNode, identity: str) -> DocumentNode:
    """Normalization 后按结构路径编号，避免根与子节点 ID 冲突。"""
    return replace(
        node,
        node_id=identity,
        children=tuple(
            _assign_structural_ids(child, f"{identity}:{index}")
            for index, child in enumerate(node.children)
        ),
    )


class _TokenTreeBuilder:
    def __init__(
        self,
        *,
        tokens: list[Token],
        text: str,
        line_offsets: list[int],
    ) -> None:
        self._tokens = tokens
        self._text = text
        self._line_offsets = line_offsets
        self._next_id = 0

    def build(self) -> tuple[DocumentNode, ...]:
        nodes, _ = self._parse_range(0, None)
        return tuple(nodes)

    def _parse_range(
        self,
        index: int,
        closing_type: str | None,
    ) -> tuple[list[DocumentNode], int]:
        nodes: list[DocumentNode] = []
        while index < len(self._tokens):
            token = self._tokens[index]
            if closing_type is not None and token.type == closing_type:
                return nodes, index + 1

            if token.nesting == 1:
                kind = _OPEN_KINDS.get(token.type)
                children, index = self._parse_range(
                    index + 1,
                    token.type.replace("_open", "_close"),
                )
                if kind is None:
                    nodes.extend(children)
                    continue
                spans = _token_spans(token, self._line_offsets, children)
                node_text = _span_text(self._text, spans, children)
                metadata = _token_metadata(token, kind)
                if kind is NodeKind.TABLE:
                    # markdown-it 没有 delimiter token；在 parser 边界保留原始
                    # header 表达，splitter 不再需要字符位置来恢复它。
                    metadata["table_header_text"] = "\n".join(
                        node_text.split("\n")[:2]
                    ).strip()
                nodes.append(
                    self._make_node(
                        kind=kind,
                        text=node_text,
                        source_spans=spans,
                        children=tuple(children),
                        metadata=metadata,
                    )
                )
                continue

            if token.nesting == 0 and (
                token.map is not None or token.type in {"fence", "math_block"}
            ):
                node = self._leaf_node(token)
                if node is not None:
                    nodes.append(node)
            index += 1

        return nodes, index

    def _leaf_node(self, token: Token) -> DocumentNode | None:
        if token.type == "fence":
            kind = NodeKind.CODE
            info = token.info.strip()
            metadata = {
                "language": info.split(maxsplit=1)[0] if info else None,
                "info": token.info,
                "markup": token.markup,
                "fenced": True,
            }
        elif token.type == "code_block":
            kind = NodeKind.CODE
            metadata = {"language": None, "fenced": False}
        elif token.type in {"math_block", "math_block_label"}:
            kind = NodeKind.FORMULA
            metadata = {}
        elif token.type == "html_block":
            if not token.content.lstrip().lower().startswith("<table"):
                return None
            kind = NodeKind.TABLE
            metadata = {"source_format": "html"}
        elif token.type == "inline":
            return self._inline_node(token)
        else:
            return None

        spans = _token_spans(token, self._line_offsets, ())
        return self._make_node(
            kind=kind,
            text=_span_text(self._text, spans, ()),
            source_spans=spans,
            metadata=metadata,
        )

    def _inline_node(self, token: Token) -> DocumentNode:
        children = tuple(
            self._make_node(
                kind=NodeKind.INLINE,
                text=child.content,
                source_spans=(),
                metadata={
                    "token_type": child.type,
                    "attrs": child.attrs,
                    "markup": child.markup,
                },
            )
            for child in token.children or ()
        )
        return self._make_node(
            kind=NodeKind.INLINE,
            text=token.content,
            source_spans=_token_spans(token, self._line_offsets, ()),
            children=children,
            metadata={"token_type": "inline"},
        )

    def _make_node(
        self,
        *,
        kind: NodeKind,
        text: str,
        source_spans: tuple[SourceSpan, ...],
        children: tuple[DocumentNode, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> DocumentNode:
        node = DocumentNode(
            node_id=f"node-{self._next_id}",
            kind=kind,
            text=text,
            source_spans=source_spans,
            children=children,
            metadata=metadata or {},
        )
        self._next_id += 1
        return node


def _markdown_line_offsets(text: str) -> list[int]:
    """建立 markdown-it 使用的按 LF 分行表，保留 CRLF 和其他字符。"""

    offsets = [0]
    for index, character in enumerate(text):
        if character == "\n":
            offsets.append(index + 1)
    if offsets[-1] != len(text):
        offsets.append(len(text))
    return offsets


def _token_spans(
    token: Token,
    line_offsets: list[int],
    children: tuple[DocumentNode, ...] | list[DocumentNode],
) -> tuple[SourceSpan, ...]:
    # markdown-it 只给 tr/inline 行范围；把整行复制给 cell 会伪造精确引用。
    if token.type in {"th_open", "td_open"}:
        return ()
    if token.map is not None:
        start_line, end_line = token.map
        return (SourceSpan(line_offsets[start_line], line_offsets[end_line]),)
    child_spans = tuple(
        span for child in children for span in child.source_spans if span.length
    )
    if not child_spans:
        return ()
    return (
        SourceSpan(
            min(span.start_offset for span in child_spans),
            max(span.end_offset for span in child_spans),
        ),
    )


def _span_text(
    source: str,
    spans: tuple[SourceSpan, ...],
    children: tuple[DocumentNode, ...] | list[DocumentNode],
) -> str:
    if spans:
        return source[spans[0].start_offset : spans[-1].end_offset]
    return "\n".join(child.text for child in children if child.text)


def _token_metadata(token: Token, kind: NodeKind) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if kind is NodeKind.LIST:
        metadata["ordered"] = token.type == "ordered_list_open"
        if token.attrs and "start" in token.attrs:
            metadata["start"] = token.attrs["start"]
    if kind is NodeKind.SECTION:
        metadata["heading_level"] = int(token.tag[1])
    if kind is NodeKind.TABLE_CELL:
        metadata["alignment"] = dict(token.attrs or {}).get("style")
    return metadata


def _normalize_nodes(
    nodes: tuple[DocumentNode, ...],
    source: str,
) -> list[DocumentNode]:
    normalized: list[DocumentNode] = []
    headings: list[tuple[int, str]] = []
    previous_heading: tuple[int, tuple[str, ...], str] | None = None

    for node in nodes:
        if node.kind is NodeKind.SECTION:
            title = _inline_content(node)
            if not title:
                continue
            level = int(node.metadata["heading_level"])
            parent_index = next(
                (
                    index
                    for index, (heading_level, _) in enumerate(headings)
                    if heading_level >= level
                ),
                len(headings),
            )
            parent_path = tuple(
                heading_title for _, heading_title in headings[:parent_index]
            )
            # 相邻同层同父路径的完全重复标题视为解析噪声，跳过
            if (
                previous_heading is not None
                and previous_heading[0] == level
                and previous_heading[1] == parent_path
                and previous_heading[2] == title
            ):
                continue
            headings = headings[:parent_index]
            headings.append((level, title))
            previous_heading = (level, parent_path, title)
            metadata = {
                **node.metadata,
                "title": title,
                "section_path": tuple(title for _, title in headings),
            }
            normalized.append(replace(node, metadata=metadata))
            continue

        metadata = {
            **node.metadata,
            "section_path": tuple(title for _, title in headings),
        }
        if node.kind is NodeKind.FORMULA:
            formula_match = FORMULA_LABEL_RE.search(node.text)
            if formula_match is not None:
                metadata["anchor_label"] = f"Equation {formula_match.group('number')}"
        normalized.append(replace(node, metadata=metadata))

    normalized = _associate_numbered_labels(normalized, source)
    return _remove_empty_headings(normalized)


def _inline_content(node: DocumentNode) -> str:
    for child in node.children:
        if child.kind is NodeKind.INLINE:
            return child.text.strip()
    return node.text.strip()


def _remove_empty_headings(nodes: list[DocumentNode]) -> list[DocumentNode]:
    headings_to_remove: set[int] = set()
    for index, node in enumerate(nodes):
        if node.kind is not NodeKind.SECTION:
            continue
        level = int(node.metadata["heading_level"])
        has_content = False
        has_child = False
        for following in nodes[index + 1 :]:
            if following.kind is NodeKind.SECTION:
                has_child = int(following.metadata["heading_level"]) > level
                break
            if following.text.strip():
                has_content = True
                break
        if not has_content and not has_child:
            headings_to_remove.add(index)

    if not headings_to_remove:
        return nodes

    result: list[DocumentNode] = []
    headings: list[tuple[int, str]] = []
    for index, node in enumerate(nodes):
        if index in headings_to_remove:
            continue
        if node.kind is NodeKind.SECTION:
            level = int(node.metadata["heading_level"])
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, str(node.metadata["title"])))
        result.append(
            replace(
                node,
                metadata={
                    **node.metadata,
                    "section_path": tuple(title for _, title in headings),
                },
            )
        )
    return result


def _associate_numbered_labels(
    nodes: list[DocumentNode],
    source: str,
) -> list[DocumentNode]:
    result: list[DocumentNode] = []
    index = 0
    while index < len(nodes):
        first = nodes[index]
        if index + 1 < len(nodes):
            second = nodes[index + 1]
            caption, target = (
                (first, second) if first.kind is NodeKind.PARAGRAPH else (second, first)
            )
            label_match = (
                _numbered_anchor(caption.text)
                if caption.kind is NodeKind.PARAGRAPH
                else None
            )
            target_kind = (
                NodeKind.TABLE
                if label_match and label_match[0] == "table"
                else NodeKind.FIGURE
                if label_match
                else None
            )
            if (
                label_match is not None
                and target.kind is target_kind
                and _spans_are_adjacent(source, first, second)
            ):
                start = min(span.start_offset for span in first.source_spans)
                end = max(span.end_offset for span in second.source_spans)
                result.append(
                    replace(
                        target,
                        text=source[start:end],
                        source_spans=(SourceSpan(start, end),),
                        children=(*target.children, caption),
                        metadata={
                            **target.metadata,
                            "anchor_label": label_match[1],
                            "caption": caption.text,
                            "figure_text": target.text,
                        },
                    )
                )
                index += 2
                continue
        result.append(first)
        index += 1
    return result


def _numbered_anchor(text: str) -> tuple[str, str] | None:
    match = NUMBERED_LABEL_RE.fullmatch(text.strip())
    if match is None:
        return None
    number = match.group("number")
    if match.group("table_label") is not None:
        return "table", f"Table {number}"
    return "figure", f"Figure {number}"


def _spans_are_adjacent(
    source: str,
    first: DocumentNode,
    second: DocumentNode,
) -> bool:
    if not first.source_spans or not second.source_spans:
        return False
    first_end = max(span.end_offset for span in first.source_spans)
    second_start = min(span.start_offset for span in second.source_spans)
    return not source[first_end:second_start].strip()
