import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.document_tools.document_parse.models import DocumentParseRequest
from chat.application.tools.document_tools.document_parse.parsers.specialized.spreadsheet import (
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
