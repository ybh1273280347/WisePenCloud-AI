from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from .chunking.chunker import Anchor, Section
from .parsing.parser import SourceSpan


@dataclass(slots=True)
class OutlineNode:
    """模型可见的精简目录节点，不暴露 offset 和内部节点树。"""

    section_id: str
    title: str
    length: int
    anchor_labels: list[str] = field(default_factory=list)
    children: list[OutlineNode] = field(default_factory=list)


class OutlineAssembler:
    """把内部文档结构投影为不含 offset/path 的模型可见目录。"""

    @staticmethod
    def assemble(
        *,
        sections: Sequence[Section],
        anchors: Sequence[Anchor],
    ) -> list[OutlineNode]:
        if not sections:
            return []

        # 先按 parent_section_id 建索引，再统一按 ordinal/原文位置排序；
        # outline 不依赖调用方传入顺序，也不使用 section_path 识别节点。
        children_by_parent: dict[str | None, list[Section]] = defaultdict(list)
        root_section: Section | None = None
        for section in sections:
            children_by_parent[section.parent_section_id].append(section)
            if section.parent_section_id is None and section.level == 0:
                root_section = section

        for children in children_by_parent.values():
            children.sort(
                key=lambda section: (
                    section.ordinal,
                    section.own_span.start_offset,
                )
            )

        if root_section is None:
            # 没有前置无标题正文时，真实顶层 Section 直接挂在文档根下。
            return [
                _to_outline_node(
                    section=section,
                    children_by_parent=children_by_parent,
                    anchors=anchors,
                )
                for section in children_by_parent[None]
            ]

        nodes: list[OutlineNode] = []
        if root_section.title:
            # 前言 root 的 subtree 覆盖全文；只投影它自己的 anchor/page，
            # 不展开子标题，避免把整棵文档树重复嵌入“文档开头”。
            nodes.append(
                _to_outline_node(
                    section=root_section,
                    children_by_parent=children_by_parent,
                    anchors=anchors,
                    expand_children=False,
                )
            )
        nodes.extend(
            _to_outline_node(
                section=section,
                children_by_parent=children_by_parent,
                anchors=anchors,
            )
            for section in children_by_parent[root_section.section_id]
        )
        return nodes


def _to_outline_node(
    *,
    section: Section,
    children_by_parent: dict[str | None, list[Section]],
    anchors: Sequence[Anchor],
    expand_children: bool = True,
) -> OutlineNode:
    # 真实章节覆盖子树，前言 root 只覆盖直属正文。
    span = section.subtree_span if section.level > 0 else section.own_span
    anchor_labels = [
        anchor.label
        for anchor in anchors
        if _overlaps(section.own_span, anchor.source_span)
    ]
    # anchor 必须与 Section 的直属范围相交，不能因为落在子 Section 中而重复归属。
    return OutlineNode(
        section_id=section.section_id,
        title=section.title,
        length=span.end_offset - span.start_offset,
        anchor_labels=anchor_labels,
        children=[
            _to_outline_node(
                section=child,
                children_by_parent=children_by_parent,
                anchors=anchors,
            )
            for child in (
                children_by_parent.get(section.section_id, [])
                if expand_children
                else []
            )
        ],
    )


def _overlaps(span: SourceSpan, other: SourceSpan) -> bool:
    return span.start_offset < other.end_offset and span.end_offset > other.start_offset
