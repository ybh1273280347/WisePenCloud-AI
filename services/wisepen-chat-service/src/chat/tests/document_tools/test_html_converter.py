from pathlib import Path

import pytest

from chat.application.tools.document_tools.document_parse.converters.html import HtmlConverter


@pytest.mark.asyncio
async def test_html_converter_preserves_document_structure_without_scripts(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.html"
    file_path.write_text(
        """
        <html>
          <head><style>.hidden { display:none }</style></head>
          <body>
            <nav>Navigation</nav>
            <h1>Title</h1>
            <ul><li>Item</li></ul>
            <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
            <a href="https://example.com">Link</a>
            <script>window.executed = true</script>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    result = await HtmlConverter().convert(file_path, file_name=file_path.name)

    assert "Title" in result.markdown
    assert "Navigation" in result.markdown
    assert "Item" in result.markdown
    assert "https://example.com" in result.markdown
    assert "window.executed" not in result.markdown
    assert "display:none" not in result.markdown
