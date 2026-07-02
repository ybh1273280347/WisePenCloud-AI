from __future__ import annotations

from functools import lru_cache
from typing import Any

from docling.document_converter import DocumentConverter
from docling_core.types.doc import ImageRefMode

from chat.application.tools.document_tools.document_parse.errors import DocumentParserError
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)


class DoclingParser:

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        try:
            result = _get_converter().convert(str(request.file_path))
            return DocumentParseResult(
                markdown=_export_docling_markdown(result.document),
            )
        except Exception as e:
            raise DocumentParserError(
                "Docling parser failed.",
                cause=e,
            ) from e


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    # 通用 Docling 解析器不限制格式；PDF 由专职策略优先接管，走不到这里。
    return DocumentConverter()


_MARKDOWN_EXPORT_OPTIONS = {
    "image_mode": ImageRefMode.EMBEDDED,
    "traverse_pictures": True,
}


def _export_docling_markdown(document: Any) -> str:
    """尽力按页导出 Docling Markdown。

    Docling 对 PDF/PPTX 等格式可能提供 pages；有页信息时逐页导出并插入统一 page marker。
    DOCX/HTML 等没有可靠页概念时，保持原始 Markdown 输出。图片保留是固定导出策略，
    不对调用方暴露 image mode 开关。
    """

    page_numbers = sorted((getattr(document, "pages", {}) or {}).keys())
    if not page_numbers:
        return str(document.export_to_markdown(**_MARKDOWN_EXPORT_OPTIONS) or "").strip()

    page_markdowns: list[str] = []
    for page_number in page_numbers:
        markdown = str(
            document.export_to_markdown(
                page_no=page_number,
                **_MARKDOWN_EXPORT_OPTIONS,
            ) or ""
        ).strip()
        page_markdowns.append(_with_page_marker(page_number, markdown))

    return "\n\n".join(part for part in page_markdowns if part.strip()).strip()


def _with_page_marker(page_number: int, markdown: str) -> str:
    marker = f"<!-- page {page_number} -->"
    return marker if not markdown else f"{marker}\n\n{markdown}"
