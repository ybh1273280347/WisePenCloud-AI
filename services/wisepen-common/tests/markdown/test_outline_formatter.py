from common.utils.markdown import MarkdownChunker, OutlineFormatter


def test_global_outline_formats_depth_children_counts_and_anchor_labels() -> None:
    source = (
        "# Alpha\n\nAlpha direct text.\n\n"
        "## Child\n\nTable 1: Measurements\n\n"
        "| Value |\n| --- |\n| 42 |\n\n"
        "### Grandchild\n\nNested text.\n\n"
        "## Sibling\n\nSibling text.\n\n"
        "# Beta\n\nBeta text.\n"
    )
    result = MarkdownChunker().chunk(source)
    formatter = OutlineFormatter(
        sections=result.sections,
        anchors=result.anchors,
    )

    outline = formatter.global_outline(max_level=2)

    assert "- Alpha {" in outline
    assert "  - Child {" in outline
    assert "  - Sibling {" in outline
    assert "Grandchild" not in outline
    assert "[+2]" in outline
    assert "[Table 1]" in outline
    assert formatter.global_outline(max_level=1).count("\n") == 1


def test_neighborhood_keeps_ancestors_marks_current_and_limits_sibling_window() -> None:
    result = MarkdownChunker().chunk(
        "# Alpha\n\nAlpha text.\n\n"
        "## Before\n\nBefore text.\n\n"
        "## Current\n\nCurrent text.\n\n"
        "### Direct child\n\nChild text.\n\n"
        "#### Deep child\n\nDeep text.\n\n"
        "## After\n\nAfter text.\n\n"
        "## Outside\n\nOutside text.\n"
    )
    current = next(section for section in result.sections if section.title == "Current")
    formatter = OutlineFormatter(
        sections=result.sections,
        anchors=result.anchors,
    )

    outline = formatter.neighborhood(current.section_id, sibling_steps=1)

    assert outline.index("- Alpha {") < outline.index("- Current {")
    assert "  - Current {" in outline and "[current]" in outline
    assert "    - Direct child {" in outline
    assert "Deep child" not in outline
    assert "Before" in outline and "After" in outline
    assert "Outside" not in outline
