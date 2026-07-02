import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)
from chat.application.tools.document_tools.document_parse.parsers.common import (
    common_document as common_document_module,
)
from chat.application.tools.document_tools.document_parse.parsers.common.common_document import (
    CommonDocumentParser,
)
from chat.application.tools.document_tools.document_parse import service as service_module
from chat.application.tools.document_tools.document_parse.service import DocumentParseService


@pytest.mark.asyncio
async def test_service_routes_xlsx_to_pandas_without_common_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _PandasParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("pandas")
            return DocumentParseResult(markdown="spreadsheet")

    class _UnexpectedCommonParser:
        async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
            calls.append("common")
            raise AssertionError("xlsx should not enter common parser chain")

    monkeypatch.setattr(
        service_module,
        "detect_file_type",
        lambda _: SimpleNamespace(label="xlsx", mime_type="application/octet-stream"),
    )
    monkeypatch.setattr(service_module, "PandasSpreadsheetParser", _PandasParser)
    monkeypatch.setattr(service_module, "CommonDocumentParser", _UnexpectedCommonParser)

    result = await DocumentParseService().parse(DocumentParseRequest(file_path="sample.xlsx"))

    assert result.markdown == "spreadsheet"
    assert calls == ["pandas"]


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
