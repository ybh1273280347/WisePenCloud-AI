from __future__ import annotations

from pathlib import Path

import pandas as pd

from chat.application.tools.document_tools.document_parse.errors import DocumentParserError
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)


class PandasSpreadsheetParser:
    """基于 pandas/openpyxl 的 xlsx 解析器。"""

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        try:
            file_path = Path(request.file_path)
            sheet_frames = pd.read_excel(
                file_path,
                sheet_name=None,
                header=0,
                dtype=object,
                engine="openpyxl",
            )

            sections: list[str] = []
            for sheet_name, frame in sheet_frames.items():
                # 每个 sheet 单独渲染，避免跨表混淆结构。
                markdown = str(frame.to_markdown(index=False) or "").strip()
                sections.append(f"## {sheet_name}\n\n{markdown}".strip())

            return DocumentParseResult(
                markdown="\n\n".join(sections).strip(),
            )
        except Exception as e:
            raise DocumentParserError(
                "Spreadsheet parser failed.",
                cause=e,
            ) from e
