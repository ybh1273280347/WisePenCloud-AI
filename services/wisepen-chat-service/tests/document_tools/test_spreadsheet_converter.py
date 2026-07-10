from pathlib import Path

import pandas as pd
import pytest

from chat.application.tools.document_tools.document_parse.converters.spreadsheet import SpreadsheetConverter


@pytest.mark.asyncio
async def test_csv_preserves_string_values_and_na_literals(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.csv"
    file_path.write_text("code,value\n00123,NA\n00001,NULL\n", encoding="utf-8")

    result = await SpreadsheetConverter().convert(file_path, file_name=file_path.name)

    assert "00123" in result.markdown
    assert "00001" in result.markdown
    assert "NA" in result.markdown
    assert "NULL" in result.markdown


@pytest.mark.asyncio
async def test_tsv_uses_tab_delimiter(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.tsv"
    file_path.write_text("name\tvalue\nrow-1\tvalue-1\n", encoding="utf-8")

    result = await SpreadsheetConverter().convert(file_path, file_name=file_path.name)

    assert "row-1" in result.markdown
    assert "value-1" in result.markdown


@pytest.mark.asyncio
async def test_xlsx_preserves_multiple_sheets_and_empty_cells(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.xlsx"
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        pd.DataFrame({"code": ["00123"], "value": [""]}).to_excel(
            writer,
            sheet_name="First",
            index=False,
        )
        pd.DataFrame({"name": ["second"]}).to_excel(
            writer,
            sheet_name="Second",
            index=False,
        )

    result = await SpreadsheetConverter().convert(file_path, file_name=file_path.name)

    assert "# Sheet: First" in result.markdown
    assert "# Sheet: Second" in result.markdown
    assert "00123" in result.markdown
    assert "NaN" not in result.markdown
