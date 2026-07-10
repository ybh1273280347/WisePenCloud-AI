from pathlib import Path
from types import SimpleNamespace

import pytest

from chat.application.tools.document_tools import document_parse_tool as tool_module
from chat.application.tools.document_tools.document_parse.core.models import DocumentParseResult
from chat.application.tools.document_tools.document_parse_tool import DocumentParseTool


class _Cache:
    def __init__(self) -> None:
        self.writes: list[str] = []

    async def read_parsed_web_cache(self, **_: object) -> None:
        return None

    async def write_direct_url_cache_stub(self, **_: object) -> bool:
        return True

    async def write_parsed_web_cache(self, *, markdown: str, **_: object) -> None:
        self.writes.append(markdown)


class _ParseService:
    async def parse(self, request: object) -> DocumentParseResult:
        path = Path(getattr(request, "file_path"))
        return DocumentParseResult(markdown=path.read_text(encoding="utf-8"))


class _FileStore:
    def __init__(self, resolved: object | None = None) -> None:
        self._resolved = resolved

    async def resolve_ref(self, **_: object) -> object:
        assert self._resolved is not None
        return self._resolved


@pytest.mark.asyncio
async def test_document_parse_consumes_file_reference_without_exposing_path(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("file content", encoding="utf-8")
    store = _FileStore(SimpleNamespace(
        path=file_path,
        filename="sample.txt",
        content_type="text/plain",
        metadata={},
    ))
    tool = DocumentParseTool(file_store=store, parse_service=_ParseService())
    tool._cache = _Cache()

    result = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        file_refs=["file_source_1"],
    )

    assert result.cacheable_texts == ("file content",)
    assert str(file_path) not in str(result.visible_result)


@pytest.mark.asyncio
async def test_document_parse_direct_url_downloads_without_intermediate_file_ref(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
) -> None:
    downloaded_path = tmp_path / "download.txt"
    downloaded_path.write_text("url content", encoding="utf-8")

    async def fake_download_url(url: str, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            source_url=url,
            status_code=200,
            headers={"content-type": "text/plain"},
            content_type="text/plain",
            downloader="test",
            file_path=str(downloaded_path),
            file_label="txt",
        )

    monkeypatch.setattr(tool_module, "validate_public_http_url", lambda url: url)
    monkeypatch.setattr(tool_module, "download_url", fake_download_url)
    tool = DocumentParseTool(
        file_store=_FileStore(),
        parse_service=_ParseService(),
        url_download_http_client=object(),
    )
    tool._cache = _Cache()

    result = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        direct_urls=["https://example.com/download.txt"],
    )

    assert result.cacheable_texts == ("url content",)
    assert not downloaded_path.exists()
