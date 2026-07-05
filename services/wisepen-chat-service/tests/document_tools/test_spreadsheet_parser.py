import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.document_tools.document_parse.models import DocumentParseRequest
from chat.application.tools.document_tools.document_parse.parsers.specialized.spreadsheet_parser import (
    PandasSpreadsheetParser,
)


@pytest.mark.asyncio
async def test_spreadsheet_parser_renders_xlsx_with_pandas_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.xlsx"
    pd.DataFrame(
        [["Name|Label", "Notes"]]
        + [[f"row-{index}", f"value-{index}"] for index in range(1, 241)]
    ).to_excel(file_path, sheet_name="Data", header=False, index=False)

    result = await PandasSpreadsheetParser().parse(
        DocumentParseRequest(file_path=file_path),
    )

    assert result.markdown.startswith("## Data\n\n| Name|Label")
    assert "row-1" in result.markdown
    assert "row-240" in result.markdown


@pytest.mark.asyncio
async def test_spreadsheet_parser_renders_csv_with_pandas_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.csv"
    file_path.write_text(
        "Name,Notes\nrow-1,value-1\nrow-2,value-2\n",
        encoding="utf-8",
    )

    result = await PandasSpreadsheetParser().parse(
        DocumentParseRequest(file_path=file_path),
    )

    assert result.markdown.startswith("## sample.csv\n\n| Name")
    assert "row-1" in result.markdown
    assert "value-2" in result.markdown


@pytest.mark.asyncio
async def test_spreadsheet_parser_renders_csv_from_mime_type(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.bin"
    file_path.write_text(
        "Name,Notes\nrow-1,value-1\nrow-2,value-2\n",
        encoding="utf-8",
    )

    result = await PandasSpreadsheetParser().parse(
        DocumentParseRequest(file_path=file_path, mime_type="text/csv"),
    )

    assert result.markdown.startswith("## sample.bin\n\n| Name")
    assert "row-1" in result.markdown
    assert "value-2" in result.markdown


@pytest.mark.asyncio
async def test_spreadsheet_parser_renders_tsv_with_pandas_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.tsv"
    file_path.write_text(
        "Name\tNotes\nrow-1\tvalue-1\nrow-2\tvalue-2\n",
        encoding="utf-8",
    )

    result = await PandasSpreadsheetParser().parse(
        DocumentParseRequest(file_path=file_path),
    )

    assert result.markdown.startswith("## sample.tsv\n\n| Name")
    assert "row-1" in result.markdown
    assert "value-2" in result.markdown
