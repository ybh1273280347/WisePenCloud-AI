from __future__ import annotations

from markitdown import MarkItDown

from chat.application.tools.document_tools.document_parse.errors import (
    DocumentParserError,
)
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)


class MarkItDownParser:
    """通用 Markdown 转换器，用于普通文档的第二解析链路。"""

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        try:
            result = MarkItDown().convert_local(str(request.file_path))
            return DocumentParseResult(
                markdown=str(result.text_content or "").strip(),
            )
        except Exception as e:
            raise DocumentParserError(
                "MarkItDown parser failed.",
                cause=e,
            ) from e
