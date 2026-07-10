from __future__ import annotations

from chat.application.tools.document_tools.document_parse.core.models import DocumentParseRequest, DocumentParseResult
from .converters.pdf import MinerUConverter
from .converters.router import DocumentConverterRouter


class DocumentParseService:
    """文档解析编排入口。"""

    def __init__(
            self,
            *,
            mineru_converter: MinerUConverter,
    ) -> None:
        self._router = DocumentConverterRouter(
            mineru_converter=mineru_converter
        )

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        return await self._router.convert(request)
