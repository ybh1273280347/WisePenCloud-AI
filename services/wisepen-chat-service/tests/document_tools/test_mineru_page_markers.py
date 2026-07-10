from chat.application.tools.document_tools.document_parse.converters.pdf.page_markers import (
    insert_page_markers,
)


def test_insert_page_markers_before_markdown_blocks() -> None:
    markdown = (
        "# Title\n\n"
        "Introduction\n\n"
        "Figure caption\n"
        "![](images/figure.jpg)\n\n"
        "```python\n"
        "print('page 3')\n"
        "```"
    )
    content_list = [
        {
            "type": "text",
            "text": "Title",
            "text_level": 1,
            "page_idx": 0,
        },
        {
            "type": "image",
            "img_path": "images/figure.jpg",
            "image_caption": ["Figure caption"],
            "page_idx": 1,
        },
        {
            "type": "code",
            "code_body": "print('page 3')",
            "page_idx": 2,
        },
    ]

    annotated = insert_page_markers(markdown, content_list)

    assert annotated == (
        "<!-- page 1 -->\n\n"
        "# Title\n\n"
        "Introduction\n\n"
        "<!-- page 2 -->\n\n"
        "Figure caption\n"
        "![](images/figure.jpg)\n\n"
        "<!-- page 3 -->\n\n"
        "```python\n"
        "print('page 3')\n"
        "```"
    )


def test_insert_page_markers_skips_empty_and_auxiliary_blocks() -> None:
    markdown = "First page\n\nSecond page"
    content_list = [
        {"type": "header", "text": "Header", "page_idx": 0},
        {"type": "text", "text": "", "page_idx": 0},
        {"type": "text", "text": "First page", "page_idx": 0},
        {"type": "page_number", "text": "2", "page_idx": 1},
        {"type": "text", "text": "Second page", "page_idx": 1},
    ]

    annotated = insert_page_markers(markdown, content_list)

    assert annotated == (
        "<!-- page 1 -->\n\nFirst page\n\n"
        "<!-- page 2 -->\n\nSecond page"
    )


def test_insert_page_markers_returns_original_for_mismatched_document() -> None:
    markdown = "# Different document"
    content_list = [
        {"type": "text", "text": "Expected title", "page_idx": 0},
    ]

    assert insert_page_markers(markdown, content_list) == markdown


def test_insert_page_markers_returns_original_for_ambiguous_anchor() -> None:
    markdown = "Repeated\n\nRepeated"
    content_list = [
        {"type": "text", "text": "Repeated", "page_idx": 0},
    ]

    assert insert_page_markers(markdown, content_list) == markdown


def test_insert_page_markers_does_not_return_partial_annotations() -> None:
    markdown = "First page\n\nUnrelated content"
    content_list = [
        {"type": "text", "text": "First page", "page_idx": 0},
        {"type": "text", "text": "Missing page", "page_idx": 1},
    ]

    assert insert_page_markers(markdown, content_list) == markdown
