from __future__ import annotations

from chat.application.tools.document_tools.document_parse.errors import (
    DocumentParseFailedError,
)
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)
from chat.application.tools.document_tools.document_parse.parsers.common_document.docling import (
    DoclingParser,
)
from chat.application.tools.document_tools.document_parse.parsers.common_document.markitdown import (
    MarkItDownParser,
)


class CommonDocumentParser:
    """普通文档解析链路：优先 Docling，失败后交给 MarkItDown。"""

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        last_error: BaseException | None = None
        for parser in (DoclingParser(), MarkItDownParser()):
            try:
                return await parser.parse(request)
            except Exception as e:
                last_error = e

        raise DocumentParseFailedError(
            "Common document parsers failed.",
            cause=last_error,
        )
