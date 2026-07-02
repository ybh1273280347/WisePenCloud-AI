from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import fitz
import pymupdf4llm
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode

from chat.application.tools.document_tools.document_parse.errors import PrimaryParserError
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseMonitorName,
    DocumentParseRequest,
    DocumentParseResult,
)


_DOCLING_PDF_MARKDOWN_EXPORT_OPTIONS = {
    "image_mode": ImageRefMode.EMBEDDED,
    "traverse_pictures": True,
}


class PdfParseStrategy:
    """PDF 解析策略：Docling 解析结构，扫描页统一用 OCR 补全。"""

    def __init__(
            self,
            *,
            ocr_client: Any | None = None,
            scan_coverage: float = 0.85,
            min_text_chars: int = 20,
    ) -> None:
        self._ocr_client = ocr_client
        self._scan_coverage = scan_coverage
        self._min_text_chars = min_text_chars

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        pdf_path = Path(request.file_path)

        try:
            try:
                docling_document = await asyncio.to_thread(
                    lambda: _get_pdf_docling_converter().convert(str(pdf_path)).document
                )
                markdown = await self._parse_with_docling_and_page_ocr(
                    pdf_path=pdf_path,
                    docling_document=docling_document,
                )
            except Exception:
                markdown = await self._parse_with_pymupdf4llm_fallback(pdf_path)

            return DocumentParseResult(markdown=markdown)

        except PrimaryParserError:
            raise
        except Exception as e:
            raise PrimaryParserError(
                "PDF parser failed.",
                parser_name=DocumentParseMonitorName.PDF,
                cause=e,
            ) from e

    async def _parse_with_docling_and_page_ocr(self, *, pdf_path: Path, docling_document: Any) -> str:
        """主链路：文本页保留 Docling 结构，扫描页在同一页位用 OCR 替换。"""
        page_kinds = self._classify_pages(pdf_path)
        page_markdowns: list[str] = []

        for page_number, page_kind in enumerate(page_kinds, start=1):
            try:
                docling_markdown = str(
                    docling_document.export_to_markdown(
                        page_no=page_number,
                        **_DOCLING_PDF_MARKDOWN_EXPORT_OPTIONS,
                    ) or ""
                ).strip()
            except Exception:
                docling_markdown = ""

            if page_kind == "scanned":
                if ocr_markdown := await self._parse_scanned_page_with_ocr(
                    pdf_path=pdf_path,
                    page_number=page_number,
                ):
                    page_markdowns.append(ocr_markdown)
                    continue

            if docling_markdown:
                page_markdowns.append(self._with_page_marker(page_number, docling_markdown))
                continue

            if rendered := await self._parse_page_with_pymupdf4llm(
                pdf_path=pdf_path,
                page_number=page_number,
            ):
                page_markdowns.append(self._with_page_marker(page_number, rendered))

        markdown = "\n\n".join(part for part in page_markdowns if part.strip()).strip()
        if not markdown:
            raise PrimaryParserError(
                "Docling PDF parser returned empty markdown.",
                parser_name=DocumentParseMonitorName.DOCLING,
            )
        return markdown

    async def _parse_with_pymupdf4llm_fallback(self, pdf_path: Path) -> str:
        """兜底链路：Docling 整体不可用时，仍按页混合 PyMuPDF4LLM 与 OCR。"""
        page_kinds = self._classify_pages(pdf_path)
        page_markdowns: list[str] = []

        for page_number, page_kind in enumerate(page_kinds, start=1):
            if page_kind == "text":
                if rendered := await self._parse_page_with_pymupdf4llm(
                    pdf_path=pdf_path,
                    page_number=page_number,
                ):
                    page_markdowns.append(self._with_page_marker(page_number, rendered))
                    continue
                if ocr_markdown := await self._parse_scanned_page_with_ocr(
                    pdf_path=pdf_path,
                    page_number=page_number,
                ):
                    page_markdowns.append(ocr_markdown)
                continue

            if ocr_markdown := await self._parse_scanned_page_with_ocr(
                pdf_path=pdf_path,
                page_number=page_number,
            ):
                page_markdowns.append(ocr_markdown)
                continue
            if rendered := await self._parse_page_with_pymupdf4llm(
                pdf_path=pdf_path,
                page_number=page_number,
            ):
                page_markdowns.append(self._with_page_marker(page_number, rendered))

        markdown = "\n\n".join(part for part in page_markdowns if part.strip()).strip()
        if not markdown:
            raise PrimaryParserError(
                "PyMuPDF4LLM PDF fallback returned empty markdown.",
                parser_name=DocumentParseMonitorName.PDF,
            )
        return markdown

    def _classify_pages(self, pdf_path: Path) -> list[Literal["text", "scanned"]]:
        with fitz.open(str(pdf_path)) as document:
            return [
                self._classify_page(document.load_page(page_index))
                for page_index in range(document.page_count)
            ]

    @staticmethod
    async def _parse_page_with_pymupdf4llm(*, pdf_path: Path, page_number: int) -> str | None:
        try:
            chunks = await asyncio.to_thread(
                pymupdf4llm.to_markdown,
                str(pdf_path),  # 逐页解析，优先保证坏页不影响其它页面。
                pages=[page_number - 1],
                page_chunks=True,
            )
        except Exception:
            return None

        if not chunks:
            return None
        return str(chunks[0].get("text") or "").strip() or None

    @staticmethod
    def _with_page_marker(page_number: int, markdown: str) -> str:
        marker = f"<!-- page {page_number} -->"
        return marker if not markdown else f"{marker}\n\n{markdown}"

    async def _parse_scanned_page_with_ocr(self, *, pdf_path: Path, page_number: int) -> str | None:
        """PDF 内部页级 OCR：主链路和兜底链路都用它补扫描页。"""
        if self._ocr_client is None:
            return None
        try:
            ocr_result = await self._ocr_client.parse_page(
                file_path=pdf_path,
                page_number=page_number,
            )
        except Exception:
            return None
        return ocr_result.markdown_with_page_marker()

    def _classify_page(self, page: fitz.Page) -> Literal["text", "scanned"]:
        """判断单页 PDF 是文本页还是扫描件页。"""
        page_area = abs(page.rect)
        if page_area == 0:
            return "scanned"

        max_image_coverage = 0.0
        for block in page.get_text("rawdict", flags=0)["blocks"]:
            if block["type"] == 1:
                coverage = abs(fitz.Rect(block["bbox"])) / page_area
                if coverage > max_image_coverage:
                    max_image_coverage = coverage

        has_dominant_image = max_image_coverage >= self._scan_coverage
        has_real_text = len(page.get_text("text").strip()) >= self._min_text_chars

        if not has_dominant_image and has_real_text:
            return "text"

        return "scanned"


@lru_cache(maxsize=1)
def _get_pdf_docling_converter() -> DocumentConverter:
    # Docling 主链路负责结构和图片抽取；扫描页文字识别统一由页级 OCR 补全。
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,
        do_ocr=False,
        generate_picture_images=True,
        images_scale=2.0,
    )
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )