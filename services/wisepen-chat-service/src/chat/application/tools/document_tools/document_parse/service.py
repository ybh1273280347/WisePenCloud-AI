from __future__ import annotations

from typing import Any

from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)
from chat.application.tools.document_tools.document_parse.parsers.common import CommonDocumentParser
from chat.application.tools.document_tools.document_parse.parsers.specialized import (
    PandasSpreadsheetParser,
    PdfParseStrategy,
)
from chat.application.tools.utils.file_type_detect import detect_file_type


class DocumentParseService:
    """文档解析编排入口。"""

    def __init__(
        self,
        *,
        ocr_client: Any | None = None,
    ) -> None:
        self._ocr_client = ocr_client

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        detected_type = detect_file_type(request.file_path)
        mime_type = (request.mime_type or detected_type.mime_type).lower()
        label = detected_type.label

        if label == "pdf" or mime_type == "application/pdf":
            return await PdfParseStrategy(ocr_client=self._ocr_client).parse(request)

        if label == "xlsx" or mime_type in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }:
            return await PandasSpreadsheetParser().parse(request)

        return await CommonDocumentParser().parse(request)
