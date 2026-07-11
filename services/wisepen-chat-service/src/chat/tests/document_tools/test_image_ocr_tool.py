from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from chat.application.tools.core import ToolExecutionError
from chat.application.tools.document_tools.image_ocr_tool import ImageOcrTool
from chat.application.tools.document_tools.ocr import OcrPageResult

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeFileStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def resolve_ref(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            path=self._path,
            filename="sample.png",
            content_type="image/png",
        )


class _FakeOcrClient:
    def __init__(self) -> None:
        self.last_file_path: Path | None = None

    async def parse_image(self, *, file_path: str | Path) -> OcrPageResult:
        self.last_file_path = Path(file_path)
        return OcrPageResult(page_number=1, markdown=f"ocr text from {Path(file_path).name}")


def _mock_image_http_client() -> httpx.AsyncClient:
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=_PNG_BYTES,
            request=_,
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


@pytest.mark.asyncio
async def test_image_ocr_file_ref_returns_markdown_content(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_PNG_BYTES)
    ocr_client = _FakeOcrClient()
    tool = ImageOcrTool(
        file_store=_FakeFileStore(image_path),
        ocr_client=ocr_client,
    )

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        file_ref="file_image",
    )

    assert result.tag == "image_ocr_result"
    assert result.visible_result == {
        "status": "success",
        "file_name": "sample.png",
        "reason": None,
    }
    assert result.cacheable_texts == ("<!-- page 1 -->\n\nocr text from sample.png",)


@pytest.mark.asyncio
async def test_image_ocr_file_path_url_deletes_downloaded_temp_file(tmp_path: Path) -> None:
    ocr_client = _FakeOcrClient()
    tool = ImageOcrTool(
        file_store=_FakeFileStore(tmp_path / "unused.png"),
        ocr_client=ocr_client,
        url_download_http_client=_mock_image_http_client(),
    )

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        file_path="https://example.com/download.png",
    )

    assert result.visible_result["status"] == "success"
    assert result.cacheable_texts[0].startswith("<!-- page 1 -->\n\nocr text from tool_download_")
    assert ocr_client.last_file_path is not None
    assert not ocr_client.last_file_path.exists()


@pytest.mark.asyncio
async def test_image_ocr_rejects_ambiguous_input(tmp_path: Path) -> None:
    tool = ImageOcrTool(
        file_store=_FakeFileStore(tmp_path / "unused.png"),
        ocr_client=_FakeOcrClient(),
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute(
            {"user_id": "u1", "session_id": "s1"},
            file_ref="file_image",
            file_path="https://example.com/image.png",
        )

    assert exc_info.value.reason == "invalid_image_ocr_input"
    assert exc_info.value.detail_reason == "Provide exactly one of file_ref or file_path."


@pytest.mark.asyncio
async def test_image_ocr_rejects_unsafe_image_url(tmp_path: Path) -> None:
    tool = ImageOcrTool(
        file_store=_FakeFileStore(tmp_path / "unused.png"),
        ocr_client=_FakeOcrClient(),
        url_download_http_client=_mock_image_http_client(),
    )

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        file_path="http://127.0.0.1/image.png",
    )

    assert result.visible_result["status"] == "failed"
    assert str(result.visible_result["reason"]).startswith("invalid_image_url:")
