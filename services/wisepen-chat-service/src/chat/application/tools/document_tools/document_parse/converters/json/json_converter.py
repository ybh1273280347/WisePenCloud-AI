from __future__ import annotations

import asyncio
import json
from pathlib import Path

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentParserError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseResult,
)
from ..utils import decode_text

_JSON_LINES_EXTENSIONS = {".jsonl", ".ndjson"}


class JsonConverter:
    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        # mime_type 属于统一 Converter 协议，JSON 路由当前仅依赖文件扩展名。
        return await asyncio.to_thread(
            self._convert,
            file_path,
            file_name,
        )

    @staticmethod
    def _convert(
            file_path: Path,
            file_name: str,
    ) -> DocumentParseResult:
        text = decode_text(file_path.read_bytes(), file_name=file_name)
        suffix = Path(file_name).suffix.lower() or file_path.suffix.lower()

        if suffix in _JSON_LINES_EXTENSIONS:
            return DocumentParseResult(
                markdown=_parse_json_lines(text, file_name),
            )

        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentParserError(
                f"Invalid JSON in {file_name} at line {exc.lineno}, "
                f"column {exc.colno}: {exc.msg}."
            ) from exc

        return DocumentParseResult(
            markdown=(
                "```json\n"
                f"{json.dumps(value, ensure_ascii=False, indent=2)}\n"
                "```"
            )
        )


def _parse_json_lines(text: str, file_name: str) -> str:
    """逐行校验并规范化 JSONL/NDJSON。"""
    normalized: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            # JSONDecodeError 的 lineno 是当前行内位置，外层行号需自行补充。
            raise DocumentParserError(
                f"Invalid JSONL in {file_name} at line {line_number}, "
                f"column {exc.colno}: {exc.msg}."
            ) from exc

        normalized.append(json.dumps(value, ensure_ascii=False))

    return "\n".join(normalized)

