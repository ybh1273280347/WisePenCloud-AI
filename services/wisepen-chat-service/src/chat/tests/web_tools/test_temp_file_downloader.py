from __future__ import annotations

from types import SimpleNamespace

import pytest

from chat.application.tools.web_tools.fetch_services.downloaders import temp_file_downloader as module
from chat.application.tools.web_tools.fetch_services.downloaders.temp_file_downloader import TempFileDownloader


@pytest.mark.asyncio
async def test_temp_file_downloader_uses_url_downloader(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_download_url(url: str, **kwargs: object) -> SimpleNamespace:
        calls.append({"url": url, **kwargs})
        return SimpleNamespace(
            source_url=url,
            status_code=200,
            content_type="application/pdf",
            headers={"content-type": "application/pdf"},
            file_path="D:/tmp/file.pdf",
            file_type=SimpleNamespace(label="pdf"),
        )

    monkeypatch.setattr(module, "download_url", fake_download_url)

    result = await TempFileDownloader(http_client=object()).download("https://example.test/file.pdf")

    assert result.fetcher == "temp_file_downloader"
    assert result.file_path == "D:/tmp/file.pdf"
    assert calls[0]["max_response_bytes"] == 52_428_800
