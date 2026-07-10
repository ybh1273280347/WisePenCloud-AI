from __future__ import annotations

import asyncio
from pathlib import Path

from chat.application.tools.document_tools.document_parse.core.errors import DocumentParserError
from chat.application.tools.document_tools.document_parse.core.models import DocumentParseResult
from .. import base


class HtmlConverter:
    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        try:
            result = await asyncio.to_thread(
                base.get_markitdown().convert_local,
                file_path
            )
        except Exception as exc:
            raise DocumentParserError(f"Failed to convert HTML document {file_name}.") from exc

        return DocumentParseResult(markdown=str(result.text_content or "").strip())
