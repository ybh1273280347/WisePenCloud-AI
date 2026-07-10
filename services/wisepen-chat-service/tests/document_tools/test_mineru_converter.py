from io import BytesIO
import json
from pathlib import Path
import zipfile

import httpx
import pytest

from chat.application.tools.document_tools.document_parse.converters.pdf import MinerUConverter
from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentTooLargeError,
    RemoteParserError,
    RemoteParserTimeoutError,
)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _converter(client: httpx.AsyncClient, **kwargs: object) -> MinerUConverter:
    options = {
        "poll_interval_seconds": 0.01,
        "task_timeout_seconds": 0.2,
        **kwargs,
    }
    return MinerUConverter(
        http_client=client,
        api_base_url="https://mineru.example",
        api_key="secret-token",
        **options,
    )


@pytest.mark.asyncio
async def test_mineru_converter_uploads_polls_and_extracts_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")
    result_zip = _zip_bytes({
        "result/full.md": "# Parsed".encode(),
        "result/sample_content_list.json": json.dumps([{
            "type": "text",
            "text": "Parsed",
            "text_level": 1,
            "page_idx": 0,
        }]).encode(),
    })
    uploaded: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/file-urls/batch":
            assert request.headers["authorization"] == "Bearer secret-token"
            return httpx.Response(200, json={"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file"]}})
        if request.url.host == "upload.example":
            uploaded.append(await request.aread())
            return httpx.Response(200)
        if request.url.path == "/api/v4/extract-results/batch/batch-1":
            return httpx.Response(200, json={"code": 0, "data": {"extract_result": [{"file_name": "sample.pdf", "state": "done", "full_zip_url": "https://download.example/result.zip"}]}})
        if request.url.host == "download.example":
            return httpx.Response(200, content=result_zip, headers={"content-length": str(len(result_zip))})
        raise AssertionError(f"Unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _converter(client).convert(file_path, file_name=file_path.name)

    assert uploaded == [b"%PDF-test"]
    assert result.markdown == "<!-- page 1 -->\n\n# Parsed"


@pytest.mark.asyncio
async def test_mineru_converter_reports_remote_failure_with_trace(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/file-urls/batch":
            return httpx.Response(200, json={"data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file"]}})
        if request.url.host == "upload.example":
            return httpx.Response(200)
        return httpx.Response(200, json={"data": {"extract_result": [{"state": "failed", "err_msg": "parse rejected", "trace_id": "trace-1"}]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteParserError, match=r"parse rejected, trace_id=trace-1"):
            await _converter(client).convert(file_path, file_name=file_path.name)


@pytest.mark.asyncio
async def test_mineru_converter_times_out_pending_task(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/file-urls/batch":
            return httpx.Response(200, json={"data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file"]}})
        if request.url.host == "upload.example":
            return httpx.Response(200)
        return httpx.Response(200, json={"data": {"extract_result": [{"state": "running"}]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteParserTimeoutError):
            await _converter(client, task_timeout_seconds=0.05).convert(file_path, file_name=file_path.name)


@pytest.mark.asyncio
async def test_mineru_converter_maps_http_error(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteParserError, match=r"HTTP 503"):
            await _converter(client).convert(file_path, file_name=file_path.name)


@pytest.mark.asyncio
async def test_mineru_converter_maps_business_error(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 4001, "msg": "quota exceeded", "trace_id": "trace-2"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteParserError, match=r"quota exceeded, trace_id=trace-2"):
            await _converter(client).convert(file_path, file_name=file_path.name)


@pytest.mark.asyncio
async def test_mineru_converter_rejects_zip_without_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")
    result_zip = _zip_bytes({"result.json": b"{}"})

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/file-urls/batch":
            return httpx.Response(200, json={"data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file"]}})
        if request.url.host == "upload.example":
            return httpx.Response(200)
        if request.url.path == "/api/v4/extract-results/batch/batch-1":
            return httpx.Response(200, json={"data": {"extract_result": [{"state": "done", "full_zip_url": "https://download.example/result.zip"}]}})
        return httpx.Response(200, content=result_zip)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteParserError, match=r"does not contain final Markdown"):
            await _converter(client).convert(file_path, file_name=file_path.name)


@pytest.mark.asyncio
async def test_mineru_converter_limits_download_size(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/file-urls/batch":
            return httpx.Response(200, json={"data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file"]}})
        if request.url.host == "upload.example":
            return httpx.Response(200)
        if request.url.path == "/api/v4/extract-results/batch/batch-1":
            return httpx.Response(200, json={"data": {"extract_result": [{"state": "done", "full_zip_url": "https://download.example/result.zip"}]}})
        return httpx.Response(200, content=b"too large", headers={"content-length": "9"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DocumentTooLargeError):
            await _converter(client, max_download_bytes=4).convert(file_path, file_name=file_path.name)
