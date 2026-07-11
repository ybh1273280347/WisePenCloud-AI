from pathlib import Path

import pytest

from chat.application.tools.document_tools.document_parse.converters import router as router_module
from chat.application.tools.document_tools.document_parse.converters.router import DocumentConverterRouter
from chat.application.tools.document_tools.document_parse.core.errors import UnsupportedDocumentFormatError
from chat.application.tools.document_tools.document_parse.core.models import DocumentParseRequest, DocumentParseResult
from chat.application.tools.utils.file_type_detect import FileType


class _Converter:
    def __init__(self, name: str) -> None:
        self.name = name

    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        return DocumentParseResult(markdown=self.name)


@pytest.mark.parametrize(
    ("file_name", "extension", "label", "mime_type", "expected"),
    (
        ("sample.pdf", "pdf", "pdf", "application/pdf", "pdf"),
        ("sample.docx", "docx", "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
        ("sample.docx", "docx", "docx", "application/zip", "docx"),
        ("sample.pptx", "pptx", "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"),
        ("sample.csv", "csv", "csv", "text/csv", "spreadsheet"),
        ("sample.xlsx", "xlsx", "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "spreadsheet"),
        ("sample.html", "html", "html", "text/html", "html"),
        ("sample.json", "json", "json", "application/json", "json"),
        ("sample.jsonl", "jsonl", "jsonl", "application/x-ndjson", "json"),
        ("sample.txt", "txt", "txt", "text/plain", "plaintext"),
        ("sample.md", "md", "txt", "text/plain", "plaintext"),
        ("sample.py", "py", "txt", "text/plain", "plaintext"),
        ("sample.env.example", "example", "txt", "text/plain", "plaintext"),
    ),
)
@pytest.mark.asyncio
async def test_router_uses_exact_converter(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        file_name: str,
        extension: str,
        label: str,
        mime_type: str,
        expected: str,
) -> None:
    file_path = tmp_path / file_name
    file_path.write_bytes(b"content")
    monkeypatch.setattr(
        router_module,
        "detect_file_type",
        lambda _, **__: FileType(label=label, mime_type=mime_type, extension=extension),
    )
    router = DocumentConverterRouter(
        mineru_converter=_Converter("pdf"),
        docx_converter=_Converter("docx"),
        pptx_converter=_Converter("pptx"),
        spreadsheet_converter=_Converter("spreadsheet"),
        html_converter=_Converter("html"),
        json_converter=_Converter("json"),
        plaintext_converter=_Converter("plaintext"),
        fallback_converter=_Converter("fallback"),
    )

    result = await router.convert(DocumentParseRequest(file_path=file_path))

    assert result.markdown == expected


@pytest.mark.asyncio
async def test_router_sends_unknown_text_to_fallback(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.unknown"
    file_path.write_text("readable text", encoding="utf-8")
    monkeypatch.setattr(
        router_module,
        "detect_file_type",
        lambda _, **__: FileType(label="unknown", mime_type="application/octet-stream", extension="unknown"),
    )
    router = DocumentConverterRouter(
        mineru_converter=_Converter("pdf"),
        fallback_converter=_Converter("fallback"),
    )

    result = await router.convert(DocumentParseRequest(file_path=file_path))

    assert result.markdown == "fallback"


@pytest.mark.asyncio
async def test_router_sends_unclassified_binary_to_fallback(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.bin"
    file_path.write_bytes(b"\x00\x01\x02")
    monkeypatch.setattr(
        router_module,
        "detect_file_type",
        lambda _, **__: FileType(label="unknown", mime_type="application/octet-stream", extension="bin"),
    )
    router = DocumentConverterRouter(
        mineru_converter=_Converter("pdf"),
        fallback_converter=_Converter("fallback"),
    )

    result = await router.convert(DocumentParseRequest(file_path=file_path))

    assert result.markdown == "fallback"


@pytest.mark.asyncio
async def test_router_rejects_explicitly_blocked_resource(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(
        router_module,
        "detect_file_type",
        lambda _, **__: FileType(label="png", mime_type="image/png", extension="png"),
    )
    router = DocumentConverterRouter(
        mineru_converter=_Converter("pdf"),
        fallback_converter=_Converter("fallback"),
    )

    with pytest.raises(UnsupportedDocumentFormatError):
        await router.convert(DocumentParseRequest(file_path=file_path))
