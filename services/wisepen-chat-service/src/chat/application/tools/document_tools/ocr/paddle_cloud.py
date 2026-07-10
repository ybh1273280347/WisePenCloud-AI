from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    """PaddleOCR 云端 API 请求配置。"""

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


class PaddleCloudClient:
    """PaddleOCR 云端版面解析客户端。"""

    __slots__ = ("_config", "_http", "_headers")

    def __init__(
            self,
            config: PaddleCloudConfig,
            *,
            http_client: httpx.AsyncClient,
    ) -> None:
        token = config.token.strip()
        if not token:
            raise OcrError("PaddleOCR token is required.")

        self._config = config
        self._http = http_client
        self._headers = {"Authorization": f"Bearer {token}"}

    async def parse_page(
            self,
            *,
            file_path: str | Path,
            page_number: int,
    ) -> OcrPageResult:
        """解析 PDF 指定页，非 PDF 文件按单张图片处理。"""
        path = Path(file_path)

        # PyMuPDF 渲染和本地文件读取都是同步操作，避免阻塞事件循环。
        image_bytes = await asyncio.to_thread(
            _render_pdf_page_to_png,
            path,
            page_number,
        ) if path.suffix.lower() == ".pdf" else await asyncio.to_thread(
            path.read_bytes
        )

        return await self._parse_bytes(
            image_bytes,
            page_number=page_number,
        )

    async def parse_image(
            self,
            *,
            file_path: str | Path,
    ) -> OcrPageResult:
        """解析单张图片，结果页码固定为 1。"""
        image_bytes = await asyncio.to_thread(Path(file_path).read_bytes)
        return await self._parse_bytes(image_bytes, page_number=1)

    async def _parse_bytes(
            self,
            image_bytes: bytes,
            *,
            page_number: int,
    ) -> OcrPageResult:
        job_id = await self._submit_job(image_bytes)
        result_url = await self._poll_job(job_id)
        results = await self._download_results(result_url)

        if not results:
            raise OcrError("PaddleOCR returned no page result.")

        # 每次只提交一张 PNG，云端结果始终取第一个；
        # page_number 只是原 PDF 页码，不能用于索引结果列表。
        result = results[0].get("result")
        layout_results = (
            result.get("layoutParsingResults")
            if isinstance(result, dict)
            else None
        )

        markdown = ""
        if isinstance(layout_results, list) and layout_results:
            first_layout = layout_results[0]
            markdown_data = (
                first_layout.get("markdown")
                if isinstance(first_layout, dict)
                else None
            )
            if isinstance(markdown_data, dict):
                markdown = str(markdown_data.get("text") or "").strip()

        return OcrPageResult(
            page_number=page_number,
            markdown=markdown,
        )

    async def _submit_job(self, image_bytes: bytes) -> str:
        response = await self._request_json(
            "POST",
            self._config.api_url,
            timeout=self._config.timeout_seconds,
            data={
                "model": self._config.model,
                "optionalPayload": json.dumps(
                    dict(self._config.optional_payload)
                ),
            },
            files={
                "file": ("image.png", image_bytes, "image/png"),
            },
        )

        data = response.get("data")
        job_id = data.get("jobId") if isinstance(data, dict) else None
        if not isinstance(job_id, str) or not job_id:
            raise OcrError("PaddleOCR response missing jobId.")

        return job_id

    async def _poll_job(self, job_id: str) -> str:
        for _ in range(self._config.max_poll_attempts):
            response = await self._request_json(
                "GET",
                f"{self._config.api_url}/{job_id}",
                timeout=_POLL_HTTP_TIMEOUT_SECONDS,
            )

            data = response.get("data")
            if not isinstance(data, dict):
                raise OcrError("PaddleOCR polling response missing data.")

            state = str(data.get("state") or "pending").strip().lower()

            if state == "done":
                result_url = data.get("resultUrl")
                json_url = (
                    result_url.get("jsonUrl")
                    if isinstance(result_url, dict)
                    else None
                )
                if not isinstance(json_url, str) or not json_url:
                    raise OcrError("PaddleOCR response missing jsonUrl.")
                return json_url

            if state == "failed":
                raise OcrError(
                    f"PaddleOCR job failed: "
                    f"{data.get('errorMsg') or 'unknown error'}."
                )

            # 未知的非终态继续轮询，兼容服务端新增 waiting/queued 等状态。
            await asyncio.sleep(self._config.poll_interval_seconds)

        raise OcrError("PaddleOCR job polling timed out.")

    async def _download_results(
            self,
            json_url: str,
    ) -> list[dict[str, Any]]:
        try:
            response = await self._http.get(
                json_url,
                timeout=_RESULT_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OcrError("PaddleOCR result download timed out.") from exc
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            suffix = f" with HTTP {status}" if status is not None else ""
            raise OcrError(
                f"PaddleOCR result download failed{suffix}."
            ) from exc

        results: list[dict[str, Any]] = []
        for line_number, line in enumerate(
                response.text.splitlines(),
                start=1,
        ):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OcrError(
                    f"PaddleOCR returned invalid JSONL at line "
                    f"{line_number}: {exc.msg}."
                ) from exc

            if not isinstance(item, dict):
                raise OcrError(
                    f"PaddleOCR returned a non-object result "
                    f"at line {line_number}."
                )

            results.append(item)

        return results

    async def _request_json(
            self,
            method: str,
            url: str,
            *,
            timeout: float,
            **kwargs: Any,
    ) -> dict[str, Any]:
        """统一处理 PaddleOCR 请求、HTTP 错误和 JSON 响应。"""
        try:
            response = await self._http.request(
                method,
                url,
                headers=self._headers,
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise OcrError(
                f"PaddleOCR {method} request timed out."
            ) from exc
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            suffix = f" with HTTP {status}" if status is not None else ""
            raise OcrError(
                f"PaddleOCR {method} request failed{suffix}."
            ) from exc
        except ValueError as exc:
            raise OcrError(
                f"PaddleOCR {method} returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise OcrError(
                f"PaddleOCR {method} returned a non-object response."
            )

        error_code = payload.get("errorCode")
        if error_code not in {None, 0, "0"}:
            raise OcrError(
                f"PaddleOCR API error {error_code}: "
                f"{payload.get('errorMsg') or 'unknown error'}."
            )

        return payload


def _render_pdf_page_to_png(
        path: Path,
        page_number: int,
) -> bytes:
    """将 PDF 指定页渲染为单张 PNG。"""
    with fitz.open(path) as document:
        page_index = page_number - 1
        if not 0 <= page_index < document.page_count:
            raise OcrError(
                f"PDF page {page_number} is out of range."
            )

        return document.load_page(page_index).get_pixmap(
            dpi=200,
            alpha=False,
        ).tobytes("png")