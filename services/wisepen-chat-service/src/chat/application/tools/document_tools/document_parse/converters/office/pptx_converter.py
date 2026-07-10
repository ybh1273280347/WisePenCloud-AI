from __future__ import annotations

import asyncio
from pathlib import Path

from chat.application.tools.document_tools.document_parse.core.errors import DocumentParserError
from chat.application.tools.document_tools.document_parse.core.models import DocumentParseResult
from .. import base
from ..utils import export_docling_markdown


class PptxConverter:
    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        try:
            result = await asyncio.to_thread(
                base.get_docling_converter().convert,
                file_path
            )
            return DocumentParseResult(
                markdown=export_docling_markdown(result.document)
            )
        except Exception as exc:
            raise DocumentParserError(f"Failed to convert PPTX document {file_name}.") from exc
