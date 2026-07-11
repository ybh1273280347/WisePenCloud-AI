import codecs
from pathlib import Path

import pytest

from chat.application.tools.document_tools.document_parse.converters.plaintext import PlaintextConverter
from chat.application.tools.document_tools.document_parse.core.errors import DocumentDecodeError


@pytest.mark.parametrize(
    ("file_name", "raw", "expected"),
    (
        ("sample.txt", b"plain text", "plain text"),
        ("sample.txt", codecs.BOM_UTF8 + "中文".encode(), "中文"),
        ("sample.md", b"# Title\n\n- item\n", "# Title\n\n- item\n"),
        ("sample.py", b"def f():\n    return 1\n", "def f():\n    return 1\n"),
    ),
)
@pytest.mark.asyncio
async def test_plaintext_converter_preserves_content(
        tmp_path: Path,
        file_name: str,
        raw: bytes,
        expected: str,
) -> None:
    file_path = tmp_path / file_name
    file_path.write_bytes(raw)

    result = await PlaintextConverter().convert(file_path, file_name=file_name)

    assert result.markdown == expected


@pytest.mark.asyncio
async def test_plaintext_converter_rejects_binary_content(tmp_path: Path) -> None:
    file_path = tmp_path / "broken.txt"
    file_path.write_bytes(b"text\x00binary\x01")

    with pytest.raises(DocumentDecodeError):
        await PlaintextConverter().convert(file_path, file_name=file_path.name)
