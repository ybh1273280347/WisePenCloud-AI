from functools import lru_cache
from pathlib import Path
from typing import Protocol

from docling.document_converter import DocumentConverter as DoclingConverter
from markitdown import MarkItDown

from chat.application.tools.document_tools.document_parse.core.models import DocumentParseResult


class DocumentConverter(Protocol):
    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        ...


@lru_cache(maxsize=1)
def get_docling_converter() -> DoclingConverter:
    return DoclingConverter()


@lru_cache(maxsize=1)
def get_markitdown() -> MarkItDown:
    return MarkItDown()
