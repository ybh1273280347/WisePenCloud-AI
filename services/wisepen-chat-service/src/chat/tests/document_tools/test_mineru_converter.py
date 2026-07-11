import json
from io import BytesIO
from pathlib import Path
import zipfile

import httpx
import pytest

from chat.application.tools.document_tools.document_parse.converters.pdf import (
    MinerUConverter,
)
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


def _converter(
        client: httpx.AsyncClient,
        **kwargs: object,
) -> MinerUConverter:
    return MinerUConverter(
        http_client=client,
        api_url="http://mineru.internal/file_parse",
        **kwargs,
    )


def _successful_zip(*, image_target: str = "images/figure.png") -> bytes:
    return _zip_bytes({
        "document/auto/document.md": (
            f"# Parsed\n\n![]({image_target})"
        ).encode(),
        "document/auto/document_content_list.json": json.dumps([{
            "type": "text",
            "text": "Parsed",
            "text_level": 1,
            "page_idx": 0,
        }]).encode(),
        "document/auto/images/figure.png": b"image-bytes",
    })


@pytest.mark.asyncio
async def test_mineru_converter_uses_run_01_form_and_embeds_result(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "download"
    file_path.write_bytes(b"%PDF-test")
    result_zip = _successful_zip()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://mineru.internal/file_parse"
        body = await request.aread()
        for name, value in {
            "backend": "pipeline",
            "parse_method": "auto",
            "formula_enable": "true",
            "table_enable": "true",
            "return_md": "true",
            "return_content_list": "true",
            "return_middle_json": "true",
            "return_model_output": "false",
            "return_images": "true",
            "response_format_zip": "true",
            "return_original_file": "false",
            "start_page_id": "0",
            "end_page_id": "99999",
        }.items():
            assert f'name="{name}"\r\n\r\n{value}'.encode() in body
        assert b'filename="1706.03762.pdf"' in body
        assert b"%PDF-test" in body
        return httpx.Response(
            200,
            content=result_zip,
            headers={"content-type": "application/zip"},
        )

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        result = await _converter(client).convert(
            file_path,
            file_name="1706.03762",
        )

    assert result.markdown.startswith("<!-- page 1 -->\n\n# Parsed")
    assert "data:image/png;base64,aW1hZ2UtYnl0ZXM=" in result.markdown
    assert "images/figure.png" not in result.markdown


@pytest.mark.asyncio
async def test_mineru_converter_preserves_pdf_upload_extension(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        assert b'filename="sample.pdf"' in body
        return httpx.Response(200, content=_zip_bytes({"full.md": b"# Parsed"}))

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        result = await _converter(client).convert(
            file_path,
            file_name="sample.pdf",
        )

    assert result.markdown == "# Parsed"


@pytest.mark.asyncio
async def test_mineru_converter_reports_http_error_detail(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "unsupported file"})

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(RemoteParserError, match="unsupported file"):
            await _converter(client).convert(file_path, file_name="sample.pdf")


@pytest.mark.asyncio
async def test_mineru_converter_maps_request_timeout(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(RemoteParserTimeoutError):
            await _converter(client).convert(file_path, file_name="sample.pdf")


@pytest.mark.asyncio
async def test_mineru_converter_rejects_non_zip_response(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not a zip")

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(RemoteParserError, match="did not return a ZIP"):
            await _converter(client).convert(file_path, file_name="sample.pdf")


@pytest.mark.asyncio
async def test_mineru_converter_rejects_zip_without_markdown(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")
    result_zip = _zip_bytes({"result.json": b"{}"})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=result_zip)

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(RemoteParserError, match="does not contain final Markdown"):
            await _converter(client).convert(file_path, file_name="sample.pdf")


@pytest.mark.asyncio
async def test_mineru_converter_limits_response_size(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"PKtoo large",
            headers={"content-length": "11"},
        )

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(DocumentTooLargeError):
            await _converter(client, max_response_bytes=4).convert(
                file_path,
                file_name="sample.pdf",
            )


@pytest.mark.asyncio
async def test_mineru_converter_rejects_missing_markdown_image(
        tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-test")
    result_zip = _zip_bytes({
        "document.md": b"![](images/missing.png)",
    })

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=result_zip)

    async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(RemoteParserError, match="references missing image"):
            await _converter(client).convert(file_path, file_name="sample.pdf")
