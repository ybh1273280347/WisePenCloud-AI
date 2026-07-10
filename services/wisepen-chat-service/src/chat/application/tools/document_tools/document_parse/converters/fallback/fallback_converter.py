from __future__ import annotations

import asyncio
from pathlib import Path

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentDecodeError,
    UnsupportedDocumentFormatError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseResult,
)
from .. import base
from ..plaintext import PlaintextConverter
from ..utils import export_docling_markdown


class FallbackConverter:
    """按 Docling → MarkItDown → 纯文本顺序尝试解析未知格式。"""

    __slots__ = ("_plaintext_converter",)

    def __init__(
            self,
            *,
            plaintext_converter: PlaintextConverter | None = None,
    ) -> None:
        self._plaintext_converter = plaintext_converter or PlaintextConverter()

    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        # Docling 优先处理其支持但未被 Router 精确分流的文档格式。
        try:
            result = await asyncio.to_thread(
                base.get_docling_converter().convert,
                file_path,
            )
            if markdown := export_docling_markdown(result.document):
                return DocumentParseResult(markdown=markdown)
        except Exception:
            pass

        # MarkItDown 作为更宽松的通用格式兜底。
        try:
            result = await asyncio.to_thread(
                base.get_markitdown().convert_local,
                file_path,
            )
            if markdown := str(result.text_content or "").strip():
                return DocumentParseResult(markdown=markdown)
        except Exception:
            pass

        # 最后尝试严格文本解码，避免未知代码或配置文件被直接拒绝。
        try:
            return await self._plaintext_converter.convert(
                file_path,
                file_name=file_name,
                mime_type=mime_type,
            )
        except DocumentDecodeError as exc:
            raise UnsupportedDocumentFormatError(
                file_name=file_name,
                extension=(
                    Path(file_name).suffix
                    or file_path.suffix
                ).lower().lstrip("."),
                mime_type=mime_type,
            ) from exc
