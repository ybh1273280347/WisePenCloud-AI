from pathlib import Path

import pytest

from chat.application.tools.document_tools.document_parse.converters import base
from chat.application.tools.document_tools.document_parse.converters.fallback import FallbackConverter
from chat.application.tools.document_tools.document_parse.core.errors import UnsupportedDocumentFormatError


class _FailingDocling:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def convert(self, file_path: Path) -> None:
        self._calls.append("docling")
        raise RuntimeError("docling failed")


class _FailingMarkItDown:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def convert_local(self, file_path: Path) -> None:
        self._calls.append("markitdown")
        raise RuntimeError("markitdown failed")


@pytest.mark.asyncio
async def test_fallback_uses_docling_then_markitdown_then_plaintext(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
) -> None:
    calls: list[str] = []
    file_path = tmp_path / "sample.unknown"
    file_path.write_text("fallback text", encoding="utf-8")
    monkeypatch.setattr(base, "get_docling_converter", lambda: _FailingDocling(calls))
    monkeypatch.setattr(base, "get_markitdown", lambda: _FailingMarkItDown(calls))

    result = await FallbackConverter().convert(file_path, file_name=file_path.name)

    assert calls == ["docling", "markitdown"]
    assert result.markdown == "fallback text"


@pytest.mark.asyncio
async def test_fallback_rejects_unknown_binary_after_generic_converters(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
) -> None:
    calls: list[str] = []
    file_path = tmp_path / "sample.unknown"
    file_path.write_bytes(b"\x00\x01\x02")
    monkeypatch.setattr(base, "get_docling_converter", lambda: _FailingDocling(calls))
    monkeypatch.setattr(base, "get_markitdown", lambda: _FailingMarkItDown(calls))

    with pytest.raises(UnsupportedDocumentFormatError):
        await FallbackConverter().convert(file_path, file_name=file_path.name)

    assert calls == ["docling", "markitdown"]
