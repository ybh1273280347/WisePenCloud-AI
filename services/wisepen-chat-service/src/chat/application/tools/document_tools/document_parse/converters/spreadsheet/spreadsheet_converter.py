from __future__ import annotations

import asyncio
import csv
from io import StringIO
from pathlib import Path

import pandas as pd

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentParseError,
    DocumentParserError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseResult,
)
from ..utils import decode_text

_DELIMITED_MIME_TYPES = {"text/csv", "text/tab-separated-values"}


class SpreadsheetConverter:
    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        try:
            # pandas 和文件读取都是同步阻塞操作，统一放入线程池。
            return await asyncio.to_thread(
                self._convert,
                file_path,
                file_name,
                mime_type,
            )
        except DocumentParseError:
            raise
        except Exception as exc:
            raise DocumentParserError(
                f"Failed to parse spreadsheet {file_name}: {exc}."
            ) from exc

    @staticmethod
    def _convert(
            file_path: Path,
            file_name: str,
            mime_type: str | None,
    ) -> DocumentParseResult:
        suffix = Path(file_name).suffix.lower() or file_path.suffix.lower()
        mime_type = (mime_type or "").partition(";")[0].strip().lower()

        if suffix in {".csv", ".tsv"} or mime_type in _DELIMITED_MIME_TYPES:
            text = decode_text(file_path.read_bytes(), file_name=file_name)

            if suffix == ".tsv" or mime_type == "text/tab-separated-values":
                delimiter = "\t"
            else:
                # CSV 允许常见逗号、分号、竖线和制表符分隔；识别失败时按逗号处理。
                try:
                    delimiter = csv.Sniffer().sniff(
                        text[:8_192],
                        delimiters=",;|\t",
                    ).delimiter
                except csv.Error:
                    delimiter = ","

            frame = pd.read_csv(
                StringIO(text),
                sep=delimiter,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
            )
            return DocumentParseResult(
                markdown=_render_sheet_frames({file_name: frame}),
            )

        # 旧版 XLS 需要 xlrd，OOXML 格式统一使用 openpyxl。
        engine = "xlrd" if suffix == ".xls" else "openpyxl"
        with pd.ExcelFile(file_path, engine=engine) as workbook:
            sheet_frames = pd.read_excel(
                workbook,
                sheet_name=None,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
            )

        return DocumentParseResult(
            markdown=_render_sheet_frames(sheet_frames),
        )


def _render_sheet_frames(
        sheet_frames: dict[str, pd.DataFrame],
) -> str:
    sections: list[str] = []

    for sheet_name, frame in sheet_frames.items():
        # fillna 兜住部分 Excel 引擎仍可能产生的 NaN。
        markdown = str(
            frame.fillna("").to_markdown(index=False) or ""
        ).strip()
        sections.append(f"# Sheet: {sheet_name}\n\n{markdown}".rstrip())

    return "\n\n".join(sections)

