from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import pandas as pd

from chat.application.tools.document_tools.document_parse.errors import DocumentParserError
from chat.application.tools.document_tools.document_parse.models import (
    DocumentParseRequest,
    DocumentParseResult,
)


class SpreadsheetParseKind(StrEnum):
    EXCEL_XML = "excel_xml"
    CSV = "csv"
    TSV = "tsv"


_OPENPYXL_EXCEL_LABELS = frozenset({
    "xlsx",
    "xlsm",
    "xltx",
    "xltm",
})
_OPENPYXL_EXCEL_MIME_TYPES = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.template.macroenabled.12",
})
_CSV_LABELS = frozenset({"csv"})
_CSV_MIME_TYPES = frozenset({
    "application/csv",
    "application/x-csv",
    "text/comma-separated-values",
    "text/csv",
    "text/x-csv",
})
_TSV_LABELS = frozenset({"tsv"})
_TSV_MIME_TYPES = frozenset({
    "application/tab-separated-values",
    "text/tab-separated-values",
    "text/tsv",
})


class PandasSpreadsheetParser:
    """基于 pandas/openpyxl 的表格解析器。"""

    async def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        try:
            file_path = Path(request.file_path)
            parse_kind = resolve_spreadsheet_parse_kind(
                file_path=file_path,
                mime_type=request.mime_type or "",
            )
            if parse_kind is None:
                raise DocumentParserError("Unsupported spreadsheet format.")

            if parse_kind == SpreadsheetParseKind.EXCEL_XML:
                sheet_frames = pd.read_excel(
                    file_path,
                    sheet_name=None,
                    header=0,
                    dtype=object,
                    engine="openpyxl",
                )
                return DocumentParseResult(
                    markdown=_render_sheet_frames(sheet_frames).strip(),
                )

            frame = pd.read_csv(
                file_path,
                sep="\t" if parse_kind == SpreadsheetParseKind.TSV else ",",
                header=0,
                dtype=object,
            )
            return DocumentParseResult(
                markdown=_render_sheet_frames({request.display_name: frame}).strip(),
            )
        except Exception as e:
            raise DocumentParserError(
                "Spreadsheet parser failed.",
                cause=e,
            ) from e


def is_supported_spreadsheet_file(
        *,
        file_path: str | Path,
        label: str,
        mime_type: str,
) -> bool:
    return resolve_spreadsheet_parse_kind(
        file_path=file_path,
        label=label,
        mime_type=mime_type,
    ) is not None


def resolve_spreadsheet_parse_kind(
        *,
        file_path: str | Path,
        label: str = "",
        mime_type: str = "",
) -> SpreadsheetParseKind | None:
    suffix = Path(file_path).suffix.lower().lstrip(".")

    if (
            suffix in _OPENPYXL_EXCEL_LABELS
            or label in _OPENPYXL_EXCEL_LABELS
            or mime_type in _OPENPYXL_EXCEL_MIME_TYPES
    ):
        return SpreadsheetParseKind.EXCEL_XML

    if (
            suffix in _TSV_LABELS
            or label in _TSV_LABELS
            or mime_type in _TSV_MIME_TYPES
    ):
        return SpreadsheetParseKind.TSV

    if (
            suffix in _CSV_LABELS
            or label in _CSV_LABELS
            or mime_type in _CSV_MIME_TYPES
    ):
        return SpreadsheetParseKind.CSV

    return None


def _render_sheet_frames(sheet_frames: dict[str, pd.DataFrame]) -> str:
    sections: list[str] = []
    for sheet_name, frame in sheet_frames.items():
        # 每个 sheet 或文本表格单独渲染，避免跨表混淆结构。
        markdown = str(frame.to_markdown(index=False) or "").strip()
        sections.append(f"## {sheet_name}\n\n{markdown}".strip())
    return "\n\n".join(sections)
