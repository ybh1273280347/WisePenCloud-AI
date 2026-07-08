from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import fitz
import httpx

from chat.application.tools.document_tools.ocr.core.errors import OcrError
from chat.application.tools.document_tools.ocr.core.models import OcrPageResult

_POLL_HTTP_TIMEOUT_SECONDS = 30.0
_RESULT_HTTP_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class PaddleCloudConfig:
    """PaddleOCR 云端 API 接口请求配置项。"""

    api_url: str = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
    token: str = ""
    model: str = "PaddleOCR-VL-1.6"
    timeout_seconds: float = 300.0
    poll_interval_seconds: float = 5.0
    max_poll_attempts: int = 60
    optional_payload: Mapping[str, Any] = field(
        default_factory=lambda: {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }
    )


class JobState(StrEnum):
    """PaddleOCR 异步任务运行状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PaddleCloudClient:
    """PaddleOCR 云端版面解析客户端（异步任务轮询模式）。"""

    def __init__(
            self,
            config: PaddleCloudConfig,
            *,
            http_client: httpx.AsyncClient,
    ) -> None:
        if not config.token:
            raise OcrError("PaddleOCR token is required.")

        self._config = config
        self._http = http_client
        self._headers = {"Authorization": f"bearer {config.token}"}

    async def parse_page(self, *, file_path: str | Path, page_number: int) -> OcrPageResult:
        """解析 PDF 文件的指定单页。"""
        path = Path(file_path)
        image_bytes = (
            _render_pdf_page_to_png(path, page_number=page_number)
            if path.suffix.lower() == ".pdf"
            else path.read_bytes()
        )
        return await self._parse_bytes(image_bytes, page_number=page_number)

    async def parse_image(self, *, file_path: str | Path) -> OcrPageResult:
        """原生图片文件解析（固定为第 1 页）。"""
        return await self._parse_bytes(Path(file_path).read_bytes(), page_number=1)

    async def _parse_bytes(self, image_bytes: bytes, *, page_number: int) -> OcrPageResult:
        job_id = await self._submit_job(image_bytes)
        json_url = await self._poll_job(job_id)
        results = await self._download_results(json_url)
        return _extract_page_result(results, page_number=page_number)

    async def _submit_job(self, image_bytes: bytes) -> str:
        data = {
            "model": self._config.model,
            "optionalPayload": json.dumps(dict(self._config.optional_payload)),
        }
        files = {"file": ("image.png", image_bytes, "image/png")}

        resp = await self._http.post(
            self._config.api_url,
            headers=self._headers,
            data=data,
            files=files,
            timeout=self._config.timeout_seconds,
        )
        resp.raise_for_status()

        result = resp.json()
        if err := result.get("errorCode"):
            raise OcrError(f"PaddleOCR API error {err}: {result.get('errorMsg')}")

        if not (job_id := result.get("data", {}).get("jobId")):
            raise OcrError("PaddleOCR response missing jobId")
        return job_id

    async def _poll_job(self, job_id: str) -> str:
        for _ in range(self._config.max_poll_attempts):
            resp = await self._http.get(
                f"{self._config.api_url}/{job_id}",
                headers=self._headers,
                timeout=_POLL_HTTP_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()

            data = resp.json().get("data", {})
            try:
                state = JobState(data.get("state", JobState.PENDING))
            except ValueError:
                state = JobState.PENDING

            if state == JobState.DONE:
                if not (json_url := data.get("resultUrl", {}).get("jsonUrl")):
                    raise OcrError("PaddleOCR response missing jsonUrl")
                return json_url

            if state == JobState.FAILED:
                raise OcrError(
                    f"PaddleOCR job failed: {data.get('errorMsg', 'Unknown error')}",
                )

            await asyncio.sleep(self._config.poll_interval_seconds)

        raise OcrError("PaddleOCR job polling timeout")

    async def _download_results(self, json_url: str) -> list[dict[str, Any]]:
        resp = await self._http.get(json_url, timeout=_RESULT_HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return [json.loads(line) for line in resp.text.strip().splitlines() if line.strip()]


def _render_pdf_page_to_png(path: Path, *, page_number: int) -> bytes:
    with fitz.open(str(path)) as doc:
        page_index = page_number - 1
        if not (0 <= page_index < doc.page_count):
            raise OcrError(f"PDF page {page_number} is out of range.")
        return doc.load_page(page_index).get_pixmap(dpi=200, alpha=False).tobytes("png")


def _extract_page_result(results: list[dict[str, Any]], *, page_number: int) -> OcrPageResult:
    page_index = page_number - 1
    if not (0 <= page_index < len(results)):
        raise OcrError(f"Page {page_number} not found in results")

    layout_results = results[page_index].get("result", {}).get("layoutParsingResults", [])
    if not layout_results:
        return OcrPageResult(page_number=page_number, markdown="")

    markdown_text = layout_results[0].get("markdown", {}).get("text", "")
    return OcrPageResult(page_number=page_number, markdown=markdown_text.strip())
