from __future__ import annotations

from pathlib import Path

from chat.application.tools.document_tools.document_parse.core.models import DocumentParseResult
from ..utils import decode_text


class PlaintextConverter:
    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        return DocumentParseResult(
            markdown=decode_text(
                file_path.read_bytes(),
                file_name=file_name
            ),
        )
