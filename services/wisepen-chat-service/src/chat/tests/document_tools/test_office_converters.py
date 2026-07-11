from pathlib import Path
from types import SimpleNamespace

import pytest
from docling_core.types.doc import ImageRefMode

from chat.application.tools.document_tools.document_parse.converters import base
from chat.application.tools.document_tools.document_parse.converters.office import DocxConverter, PptxConverter


class _Document:
    def export_to_markdown(self, **kwargs: object) -> str:
        assert kwargs["image_mode"] == ImageRefMode.EMBEDDED
        assert kwargs["traverse_pictures"] is True
        return "# Title\n\n![image](data:image/png;base64,AAAA)"


class _DoclingConverter:
    def convert(self, file_path: Path) -> SimpleNamespace:
        return SimpleNamespace(document=_Document())


@pytest.mark.parametrize(
    ("converter", "file_name"),
    (
        (DocxConverter(), "sample.docx"),
        (PptxConverter(), "sample.pptx"),
    ),
)
@pytest.mark.asyncio
async def test_office_converter_embeds_images_without_local_paths(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        converter: DocxConverter | PptxConverter,
        file_name: str,
) -> None:
    file_path = tmp_path / file_name
    file_path.write_bytes(b"office")
    monkeypatch.setattr(base, "get_docling_converter", lambda: _DoclingConverter())

    result = await converter.convert(file_path, file_name=file_name)

    assert "data:image/png;base64,AAAA" in result.markdown
    assert str(tmp_path) not in result.markdown
