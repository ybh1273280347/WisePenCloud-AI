from pathlib import Path

import pytest

from chat.application.tools.document_tools.document_parse.converters.json import JsonConverter
from chat.application.tools.document_tools.document_parse.core.errors import DocumentParserError


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ('{"key":"值"}', '```json\n{\n  "key": "值"\n}\n```'),
        ('[1,2]', '```json\n[\n  1,\n  2\n]\n```'),
        ('true', '```json\ntrue\n```'),
    ),
)
@pytest.mark.asyncio
async def test_json_converter_normalizes_json(tmp_path: Path, content: str, expected: str) -> None:
    file_path = tmp_path / "sample.json"
    file_path.write_text(content, encoding="utf-8")

    result = await JsonConverter().convert(file_path, file_name=file_path.name)

    assert result.markdown == expected


@pytest.mark.asyncio
async def test_json_converter_reports_line_and_column(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.json"
    file_path.write_text('{"key":}', encoding="utf-8")

    with pytest.raises(DocumentParserError, match=r"line 1, column 8"):
        await JsonConverter().convert(file_path, file_name=file_path.name)


@pytest.mark.asyncio
async def test_jsonl_converter_preserves_line_semantics(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.jsonl"
    file_path.write_text('{"a":1}\n\n[2,3]\n', encoding="utf-8")

    result = await JsonConverter().convert(file_path, file_name=file_path.name)

    assert result.markdown == '{"a": 1}\n[2, 3]'


@pytest.mark.asyncio
async def test_jsonl_converter_reports_source_line(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.ndjson"
    file_path.write_text('{"a":1}\n\n{"b":}\n', encoding="utf-8")

    with pytest.raises(DocumentParserError, match=r"line 3"):
        await JsonConverter().convert(file_path, file_name=file_path.name)
