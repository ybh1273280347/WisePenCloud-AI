import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.document_tools.ocr import OcrPageResult
from chat.application.tools.document_tools.document_parse.parsers.common_document.docling import (
    _export_docling_markdown,
)
from chat.application.tools.document_tools.document_parse.parsers.specialized.pdf import PdfParseStrategy


class _FakeDoclingDocument:
    pages = {1: object(), 2: object()}

    def export_to_markdown(self, *, page_no: int | None = None, **_: object) -> str:
        return {
            1: "page one",
            2: "| a | b |\n| - | - |\n| 1 | 2 |",
        }[page_no]


def test_export_docling_pdf_with_page_markers() -> None:
    markdown = _export_docling_markdown(_FakeDoclingDocument())

    assert markdown == (
        "<!-- page 1 -->\n\n"
        "page one\n\n"
        "<!-- page 2 -->\n\n"
        "| a | b |\n| - | - |\n| 1 | 2 |"
    )


class _FakeDoclingDocumentWithoutPages:
    def export_to_markdown(self, **_: object) -> str:
        return "plain markdown"


def test_export_docling_without_pages_keeps_original_markdown() -> None:
    markdown = _export_docling_markdown(_FakeDoclingDocumentWithoutPages())

    assert markdown == "plain markdown"


class _FakeOcrClient:
    async def parse_page(self, *, file_path: str | Path, page_number: int) -> OcrPageResult:
        return OcrPageResult(page_number=page_number, markdown=f"ocr page {page_number}")


class _FakePdfPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self, kind: str) -> str:
        assert kind == "text"
        return self._text


def test_pdf_page_classification_only_uses_empty_text() -> None:
    parser = PdfParseStrategy()

    assert parser._classify_page(_FakePdfPage("caption near a large image")) == "text"
    assert parser._classify_page(_FakePdfPage("  \n  ")) == "scanned"


@pytest.mark.asyncio
async def test_pdf_scanned_page_ocr_helper_adds_page_marker() -> None:
    markdown = await PdfParseStrategy(ocr_client=_FakeOcrClient())._parse_scanned_page_with_ocr(
        pdf_path=Path("fake.pdf"),
        page_number=3,
    )

    assert markdown == "<!-- page 3 -->\n\nocr page 3"


@pytest.mark.asyncio
async def test_pdf_scanned_page_ocr_helper_skips_without_client() -> None:
    markdown = await PdfParseStrategy(ocr_client=None)._parse_scanned_page_with_ocr(
        pdf_path=Path("fake.pdf"),
        page_number=3,
    )

    assert markdown is None


class _FakeDoclingPdfDocument:
    def export_to_markdown(self, *, page_no: int, **_: object) -> str:
        return {
            1: "docling page 1",
            2: "<!-- image -->",
            3: "",
        }[page_no]


class _MixedPdfParseStrategy(PdfParseStrategy):
    def _classify_pages(self, pdf_path: Path) -> list[str]:
        return ["text", "scanned", "text"]

    @staticmethod
    async def _parse_page_with_pymupdf4llm(*, pdf_path: Path, page_number: int) -> str | None:
        return {1: "pymupdf page 1", 3: "pymupdf page 3"}.get(page_number)


@pytest.mark.asyncio
async def test_pdf_docling_main_path_mixes_page_level_ocr_and_text_fallback() -> None:
    markdown = await _MixedPdfParseStrategy(ocr_client=_FakeOcrClient())._parse_with_docling_and_page_ocr(
        pdf_path=Path("fake.pdf"),
        docling_document=_FakeDoclingPdfDocument(),
    )

    assert markdown == (
        "<!-- page 1 -->\n\n"
        "docling page 1\n\n"
        "<!-- page 2 -->\n\n"
        "ocr page 2\n\n"
        "<!-- page 3 -->\n\n"
        "pymupdf page 3"
    )
