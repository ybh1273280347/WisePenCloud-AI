from __future__ import annotations

from typing import Any

from chat.application.tools.document_tools.document_parse.errors import DocumentParserError
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)


class ImageOcrParser:
    """图片 OCR parser，实际识别能力由注入的 OCR client 提供。"""

    def __init__(self, *, ocr_client: Any | None = None) -> None:
        self._ocr_client = ocr_client

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        if self._ocr_client is None:
            raise DocumentParserError(
                "Image OCR parser requires an OCR client.",
            )
        try:
            page = await self._ocr_client.parse_image(file_path=request.file_path)
            return DocumentParseResult(
                markdown=page.markdown_with_page_marker(),
            )
        except DocumentParserError:
            raise
        except Exception as e:
            raise DocumentParserError(
                "Image OCR parser failed.",
                cause=e,
            ) from e
