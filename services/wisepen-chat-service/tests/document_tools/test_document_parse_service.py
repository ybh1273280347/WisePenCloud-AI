import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)
from chat.application.tools.document_tools.document_parse.parsers.common_document import (
    common_document as common_document_module,
)
from chat.application.tools.document_tools.document_parse.parsers.common_document.common_document import (
    CommonDocumentParser,
)
from chat.application.tools.document_tools.document_parse import service as service_module
from chat.application.tools.document_tools.document_parse.service import DocumentParseService


@pytest.mark.parametrize(
    ("filename", "label", "mime_type"),
    (
        ("sample.xlsx", "xlsx", "application/octet-stream"),
        ("sample.xlsm", "xlsm", "application/octet-stream"),
        ("sample.xltx", "xltx", "application/octet-stream"),
        ("sample.xltm", "xltm", "application/octet-stream"),
        ("sample.csv", "csv", "application/octet-stream"),
        ("sample.tsv", "tsv", "application/octet-stream"),
        ("sample.bin", "bin", "text/csv; charset=utf-8"),
        ("sample.bin", "bin", "text/tab-separated-values; charset=utf-8"),
    ),
)
@pytest.mark.asyncio
async def test_service_routes_supported_spreadsheets_to_pandas_without_common_fallback(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    label: str,
    mime_type: str,
) -> None:
    calls: list[str] = []

    class _PandasParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("pandas")
            assert request.mime_type == mime_type.split(";", maxsplit=1)[0].lower()
            return DocumentParseResult(markdown="spreadsheet")

    class _UnexpectedCommonParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("common")
            raise AssertionError("xlsx should not enter common parser chain")

    monkeypatch.setattr(
        service_module,
        "detect_file_type",
        lambda _: SimpleNamespace(label=label, mime_type=mime_type),
    )
    monkeypatch.setattr(service_module, "PandasSpreadsheetParser", _PandasParser)
    monkeypatch.setattr(service_module, "CommonDocumentParser", _UnexpectedCommonParser)

    result = await DocumentParseService().parse(DocumentParseRequest(file_path=filename))

    assert result.markdown == "spreadsheet"
    assert calls == ["pandas"]


@pytest.mark.asyncio
async def test_service_does_not_route_unsupported_excel_formats_to_pandas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _UnexpectedPandasParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("pandas")
            raise AssertionError("unsupported excel formats should stay on common parser chain")

    class _CommonParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("common")
            return DocumentParseResult(markdown="common")

    monkeypatch.setattr(
        service_module,
        "detect_file_type",
        lambda _: SimpleNamespace(label="xls", mime_type="application/vnd.ms-excel"),
    )
    monkeypatch.setattr(service_module, "PandasSpreadsheetParser", _UnexpectedPandasParser)
    monkeypatch.setattr(service_module, "CommonDocumentParser", _CommonParser)

    result = await DocumentParseService().parse(DocumentParseRequest(file_path="sample.xls"))

    assert result.markdown == "common"
    assert calls == ["common"]


@pytest.mark.asyncio
async def test_service_routes_common_files_to_common_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _CommonParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("common")
            return DocumentParseResult(markdown="common")

    monkeypatch.setattr(
        service_module,
        "detect_file_type",
        lambda _: SimpleNamespace(label="txt", mime_type="text/plain"),
    )
    monkeypatch.setattr(service_module, "CommonDocumentParser", _CommonParser)

    result = await DocumentParseService().parse(DocumentParseRequest(file_path="sample.txt"))

    assert result.markdown == "common"
    assert calls == ["common"]


@pytest.mark.asyncio
async def test_common_parser_uses_markitdown_only_after_docling_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _FailingDoclingParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("docling")
            raise RuntimeError("docling failed")

    class _MarkItDownParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("markitdown")
            return DocumentParseResult(markdown="fallback")

    monkeypatch.setattr(common_document_module, "DoclingParser", _FailingDoclingParser)
    monkeypatch.setattr(common_document_module, "MarkItDownParser", _MarkItDownParser)

    result = await CommonDocumentParser().parse(DocumentParseRequest(file_path="sample.txt"))

    assert result.markdown == "fallback"
    assert calls == ["docling", "markitdown"]
