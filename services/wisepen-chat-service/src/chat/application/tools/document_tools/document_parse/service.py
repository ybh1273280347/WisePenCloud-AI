from __future__ import annotations

from dataclasses import replace
from typing import Any

from chat.application.tools.document_tools.document_parse.core.models import DocumentParseRequest, DocumentParseResult
from chat.application.tools.utils.file_type_detect import detect_file_type
from .parsers.common_document import CommonDocumentParser
from .parsers.specialized import PdfParser
from .parsers.specialized.spreadsheet_parser import (
    PandasSpreadsheetParser,
    is_supported_spreadsheet_file,
)


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
        mime_type = (request.mime_type or detected_type.mime_type).split(";", maxsplit=1)[0].lower()
        label = detected_type.label

        if label == "pdf" or mime_type == "application/pdf":
            return await PdfParser(ocr_client=self._ocr_client).parse(request)

        if is_supported_spreadsheet_file(
                file_path=request.file_path,
                label=label,
                mime_type=mime_type,
        ):
            parser_request = replace(request, mime_type=mime_type)
            return await PandasSpreadsheetParser().parse(parser_request)

        return await CommonDocumentParser().parse(request)
