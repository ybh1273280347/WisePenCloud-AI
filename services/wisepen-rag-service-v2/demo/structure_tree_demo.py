"""生成一段可直接验证的 section-first 目录示例输出。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rag.application.rag.index.constructor.revisions import create_content_revision
from rag.application.rag.index.constructor.structure import parse_document_structure
from rag.application.rag.read.outline_view import build_document_outline_result
from rag.domain.models.content import DocumentStructureResult
from rag.domain.models.structure import PageRange, Section


def main() -> None:
    markdown = _sample_markdown()
    structure = parse_document_structure(
        resource_id="demo-resource",
        content_revision="demo-revision",
        markdown=markdown,
    )
    revision = create_content_revision(
        resource_id="demo-resource",
        document_version=1,
        markdown=markdown,
        structure=structure,
    )
    outline = build_document_outline_result(
        DocumentStructureResult(
            revision=revision,
            sections=structure.sections,
            section_tree=[],
            pages=structure.pages,
        )
    )

    output_path = Path(__file__).with_name("structure_tree_demo_output.txt")
    output_path.write_text(
        "\n".join(
            [
                "=== 原始长文本 ===",
                markdown,
                "",
                "=== parse_document_structure 结果 ===",
                json.dumps(
                    {
                        "mode": structure.mode.value,
                        "total_length": structure.total_length,
                        "pages": [_page_dict(page) for page in structure.pages],
                        "sections": [_section_dict(section) for section in structure.sections],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "",
                "=== getDocumentStructure 可直接返回的 outline ===",
                json.dumps(
                    {
                        "resource_id": outline.revision.resource_id,
                        "document_version": outline.revision.document_version,
                        "content_revision": outline.revision.content_revision,
                        "structure_mode": outline.revision.structure_mode.value,
                        "total_length": outline.revision.total_length,
                        "outline": [_outline_dict(node) for node in outline.outline],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "",
                "=== 你该怎么看这份输出 ===",
                "1. structure.sections 是扁平事实：每个 Section 都有 own_span / subtree_span。",
                "2. outline 是给 AI 的目录：section 只出现一次，页码作为边界信息附着在节点上。",
                "3. 这里保留 breadcrumbs，但不再暴露 page-first 的地图结构。",
                "4. READ 的 getDocumentStructure 先给目录；",
                "   GET getSectionContent 再按 section_id 读正文；",
                "   EXPAND 只处理 navigation state 已发现的 Section。",
            ]
        ),
        encoding="utf-8",
    )
    print(output_path)


def _sample_markdown() -> str:
    return """# Demo 文档

这是前言。它不属于任何标题节点的正文，但会落入 root section 的 subtree_span。

<!-- page 1 -->

## 一、背景

这里是背景说明的第一段。

这里是背景说明的第二段，继续给后面的章节提供上下文。

### 一.1 现状

现状部分会跨页，并且保留自己的 own_span。

<!-- page 2 -->

### 一.2 问题

问题部分说明为什么需要标题树和正文分离。

## 二、方案

这里开始进入方案主线。

### 二.1 读取

读取能力只负责把 section_id 映射成正文。

### 二.2 展开

展开能力只处理已发现节点，不接受任意 section_id。

<!-- page 3 -->

#### 二.2.1 继续展开

这一层只是为了演示更深的 section_path。

## 三、结论

最后一章总结一下。
"""


def _section_dict(section: Section) -> dict[str, object]:
    return {
        "section_id": section.section_id,
        "title": section.title,
        "level": section.level,
        "parent_section_id": section.parent_section_id,
        "ordinal": section.ordinal,
        "section_path": section.section_path,
        "own_span": _span_dict(section.own_span),
        "subtree_span": _span_dict(section.subtree_span),
        "preview": section.preview,
    }


def _page_dict(page: PageRange) -> dict[str, object]:
    return {
        "page_label": page.page_label,
        "source_span": _span_dict(page.source_span),
    }


def _outline_dict(node) -> dict[str, object]:
    return {
        "section_id": node.section_id,
        "title": node.title,
        "level": node.level,
        "breadcrumbs": node.breadcrumbs,
        "start_page_label": node.start_page_label,
        "end_page_label": node.end_page_label,
        "children": [_outline_dict(child) for child in node.children],
    }


def _span_dict(span) -> dict[str, int]:
    return {
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
    }


if __name__ == "__main__":
    main()
