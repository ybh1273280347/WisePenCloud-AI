import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.core import ToolExecutionError
from chat.application.tools.document_tools.image_ocr_tool import ImageOcrTool
from chat.application.tools.document_tools.ocr import OcrPageResult
from chat.application.tools.utils.url_fetcher import RawFetchOutput

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
    async def parse_image(self, *, file_path: str | Path) -> OcrPageResult:
        return OcrPageResult(page_number=1, markdown=f"ocr text from {Path(file_path).name}")


class _FakeFetcher:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def name(self) -> str:
        return "fake"

    async def fetch(self, url: str) -> RawFetchOutput:
        return RawFetchOutput(
            source_url=url,
            final_url=url,
            fetcher=self.name,
            content_type="image/png",
            file_path=str(self._path),
            file_label="png",
        )


@pytest.mark.asyncio
async def test_image_ocr_file_ref_returns_markdown_content(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_PNG_BYTES)
    tool = ImageOcrTool(
        file_store=_FakeFileStore(image_path),
        ocr_client=_FakeOcrClient(),
    )

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        file_ref="tfile_image",
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
    image_path = tmp_path / "download.png"
    image_path.write_bytes(_PNG_BYTES)
    tool = ImageOcrTool(
        file_store=_FakeFileStore(image_path),
        ocr_client=_FakeOcrClient(),
        direct_fetcher=_FakeFetcher(image_path),
    )

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        file_path="https://example.test/download.png",
    )

    assert result.visible_result["status"] == "success"
    assert result.cacheable_texts == ("<!-- page 1 -->\n\nocr text from download.png",)
    assert not image_path.exists()


@pytest.mark.asyncio
async def test_image_ocr_rejects_ambiguous_input(tmp_path: Path) -> None:
    tool = ImageOcrTool(
        file_store=_FakeFileStore(tmp_path / "unused.png"),
        ocr_client=_FakeOcrClient(),
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute(
            {"user_id": "u1", "session_id": "s1"},
            file_ref="tfile_image",
            file_path="https://example.test/image.png",
        )

    assert exc_info.value.reason == "invalid_image_ocr_input"
