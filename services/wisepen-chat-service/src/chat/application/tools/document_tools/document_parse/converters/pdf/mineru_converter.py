from __future__ import annotations

import asyncio
import json
import tempfile
import time
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any

import anyio
import httpx

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentTooLargeError,
    RemoteParserError,
    RemoteParserTimeoutError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseResult,
)
from .page_markers import insert_page_markers
from ..utils import decode_text

_UPLOAD_ENDPOINT = "/api/v4/file-urls/batch"
_RESULT_ENDPOINT = "/api/v4/extract-results/batch/{batch_id}"

_PENDING_STATES = frozenset({
    "pending",
    "waiting",
    "queued",
    "running",
    "processing",
})
_FAILED_STATES = frozenset({"failed", "error"})
_SUCCESS_CODES = frozenset({0, 200, "0", "200"})
_STREAM_CHUNK_SIZE = 1024 * 1024


class MinerUConverter:
    __slots__ = (
        "_http_client",
        "_api_base_url",
        "_api_key",
        "_model_version",
        "_poll_interval_seconds",
        "_task_timeout_seconds",
        "_upload_timeout_seconds",
        "_download_timeout_seconds",
        "_max_download_bytes",
    )

    def __init__(
            self,
            *,
            http_client: httpx.AsyncClient,
            api_base_url: str,
            api_key: str,
            model_version: str | None = None,
            poll_interval_seconds: float = 2.0,
            task_timeout_seconds: float = 600.0,
            upload_timeout_seconds: float = 120.0,
            download_timeout_seconds: float = 120.0,
            max_download_bytes: int = 104_857_600,
    ) -> None:
        self._http_client = http_client
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key.strip()
        self._model_version = model_version.strip() if model_version else None
        self._poll_interval_seconds = max(0.01, float(poll_interval_seconds))
        self._task_timeout_seconds = max(0.05, float(task_timeout_seconds))
        self._upload_timeout_seconds = max(0.1, float(upload_timeout_seconds))
        self._download_timeout_seconds = max(0.1, float(download_timeout_seconds))
        self._max_download_bytes = max(1, int(max_download_bytes))

    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        # mime_type 属于统一 Converter 协议；MinerU 上传当前不依赖该字段。
        if not self._api_key:
            raise RemoteParserError("MinerU API key is not configured.")

        batch_id, upload_url = await self._request_upload(file_name)
        await self._upload_file(file_path, upload_url)
        result_url = await self._wait_for_result(batch_id, file_name)
        markdown = await self._download_markdown(result_url, file_name)

        return DocumentParseResult(markdown=markdown)

    async def _request_upload(
            self,
            file_name: str,
    ) -> tuple[str, str]:
        payload: dict[str, Any] = {
            "language": "ch",
            "files": [{
                "name": file_name,
                "is_ocr": True,
            }],
        }
        if self._model_version:
            payload["model_version"] = self._model_version

        response = await self._request_json(
            "POST",
            _UPLOAD_ENDPOINT,
            json=payload,
            timeout=self._upload_timeout_seconds,
        )

        data = response.get("data")
        if not isinstance(data, dict):
            raise RemoteParserError(
                "MinerU upload initialization returned no data: "
                f"{_response_detail(response)}."
            )

        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls")
        if (
                not isinstance(batch_id, str)
                or not batch_id
                or not isinstance(file_urls, list)
                or len(file_urls) != 1
        ):
            raise RemoteParserError(
                "MinerU upload initialization returned an invalid payload: "
                f"{_response_detail(response)}."
            )

        # 兼容 MinerU 返回纯 URL 或带 url/upload_url 字段的对象。
        signed_url = file_urls[0]
        if isinstance(signed_url, dict):
            signed_url = signed_url.get("url") or signed_url.get("upload_url")

        if not isinstance(signed_url, str) or not signed_url:
            raise RemoteParserError(
                "MinerU upload initialization returned an invalid signed URL."
            )

        return batch_id, signed_url

    async def _upload_file(
            self,
            file_path: Path,
            upload_url: str,
    ) -> None:
        try:
            response = await self._http_client.put(
                upload_url,
                content=_iter_file_chunks(file_path),
                headers={"Content-Length": str(file_path.stat().st_size)},
                timeout=_http_timeout(self._upload_timeout_seconds),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RemoteParserTimeoutError(
                "MinerU file upload timed out."
            ) from exc
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            suffix = f" with HTTP {status}" if status is not None else ""
            raise RemoteParserError(
                f"MinerU file upload failed{suffix}."
            ) from exc

    async def _wait_for_result(
            self,
            batch_id: str,
            file_name: str,
    ) -> str:
        deadline = time.monotonic() + self._task_timeout_seconds

        while (remaining := deadline - time.monotonic()) > 0:
            response = await self._request_json(
                "GET",
                _RESULT_ENDPOINT.format(batch_id=batch_id),
                # 单次请求不能突破整个解析任务的剩余时间。
                timeout=min(self._download_timeout_seconds, remaining),
            )

            data = response.get("data")
            results = (
                data.get("extract_result")
                if isinstance(data, dict)
                else None
            )

            if isinstance(results, list) and results:
                items = [
                    item
                    for item in results
                    if isinstance(item, dict)
                ]
                if not items:
                    raise RemoteParserError(
                        "MinerU result payload did not contain a file result."
                    )

                # 当前批次只上传一个文件；优先按文件名匹配，否则取唯一批次结果。
                item = next(
                    (
                        candidate
                        for candidate in items
                        if candidate.get("file_name") == file_name
                    ),
                    items[0],
                )
                state = str(item.get("state") or "").strip().lower()

                if state == "done":
                    result_url = item.get("full_zip_url")
                    if not isinstance(result_url, str) or not result_url:
                        raise RemoteParserError(
                            "MinerU completed without a result URL: "
                            f"{_response_detail(item)}."
                        )
                    return result_url

                if state in _FAILED_STATES:
                    raise RemoteParserError(
                        f"MinerU parsing failed: {_response_detail(item)}."
                    )

                if state and state not in _PENDING_STATES:
                    raise RemoteParserError(
                        f"MinerU returned unsupported task state {state}: "
                        f"{_response_detail(item)}."
                    )

            # 避免最后一次 sleep 无意义地越过任务截止时间。
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(
                    min(self._poll_interval_seconds, remaining)
                )

        raise RemoteParserTimeoutError(
            "MinerU parsing timed out after "
            f"{self._task_timeout_seconds:g} seconds."
        )

    async def _download_markdown(
            self,
            result_url: str,
            file_name: str,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="mineru_result_") as temp_dir:
            zip_path = Path(temp_dir) / "result.zip"

            try:
                async with self._http_client.stream(
                        "GET",
                        result_url,
                        timeout=_http_timeout(self._download_timeout_seconds),
                ) as response:
                    response.raise_for_status()

                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise RemoteParserError(
                                "MinerU result returned an invalid content length."
                            ) from exc

                        if declared_size > self._max_download_bytes:
                            raise DocumentTooLargeError(
                                f"MinerU result for {file_name} exceeds "
                                f"{self._max_download_bytes} bytes."
                            )

                    written = 0
                    async with await anyio.open_file(zip_path, "wb") as output:
                        async for chunk in response.aiter_bytes(
                                chunk_size=_STREAM_CHUNK_SIZE,
                        ):
                            written += len(chunk)
                            if written > self._max_download_bytes:
                                raise DocumentTooLargeError(
                                    f"MinerU result for {file_name} exceeds "
                                    f"{self._max_download_bytes} bytes."
                                )
                            await output.write(chunk)

            except DocumentTooLargeError:
                raise
            except httpx.TimeoutException as exc:
                raise RemoteParserTimeoutError(
                    "MinerU result download timed out."
                ) from exc
            except httpx.HTTPError as exc:
                status = (
                    exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None
                )
                suffix = f" with HTTP {status}" if status is not None else ""
                raise RemoteParserError(
                    f"MinerU result download failed{suffix}."
                ) from exc

            return await asyncio.to_thread(
                _extract_markdown_from_zip,
                zip_path,
                file_name,
                self._max_download_bytes,
            )

    async def _request_json(
            self,
            method: str,
            endpoint: str,
            *,
            timeout: float,
            **kwargs: Any,
    ) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        })

        try:
            response = await self._http_client.request(
                method,
                f"{self._api_base_url}{endpoint}",
                headers=headers,
                timeout=_http_timeout(timeout),
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RemoteParserTimeoutError(
                f"MinerU {method} {endpoint} timed out."
            ) from exc
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            suffix = f" with HTTP {status}" if status is not None else ""
            raise RemoteParserError(
                f"MinerU {method} {endpoint} failed{suffix}."
            ) from exc
        except ValueError as exc:
            raise RemoteParserError(
                f"MinerU {method} {endpoint} returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise RemoteParserError(
                f"MinerU {method} {endpoint} returned a non-object response."
            )

        code = payload.get("code")
        if code is not None and code not in _SUCCESS_CODES:
            raise RemoteParserError(
                f"MinerU {method} {endpoint} returned a business error: "
                f"{_response_detail(payload)}."
            )

        return payload


async def _iter_file_chunks(
        file_path: Path,
) -> AsyncIterator[bytes]:
    """按固定块大小流式读取上传文件，避免将完整 PDF 载入内存。"""
    async with await anyio.open_file(file_path, "rb") as source:
        while chunk := await source.read(_STREAM_CHUNK_SIZE):
            yield chunk


def _response_detail(payload: dict[str, Any]) -> str:
    reason = (
        payload.get("err_msg")
        or payload.get("msg")
        or payload.get("message")
        or payload.get("error")
    )
    trace_id = payload.get("trace_id") or payload.get("request_id")

    parts = [str(reason)] if reason else []
    if trace_id:
        parts.append(f"trace_id={trace_id}")

    return ", ".join(parts) or "no error detail"


def _extract_markdown_from_zip(
        zip_path: Path,
        file_name: str,
        max_markdown_bytes: int,
) -> str:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            markdown_files = [
                info
                for info in archive.infolist()
                if (
                    not info.is_dir()
                    and PurePosixPath(info.filename).suffix.lower() == ".md"
                )
            ]

            # MinerU 标准结果优先使用 full.md；否则只接受唯一 Markdown。
            selected = next(
                (
                    info
                    for info in markdown_files
                    if PurePosixPath(info.filename).name.lower() == "full.md"
                ),
                None,
            ) or (
                markdown_files[0]
                if len(markdown_files) == 1
                else None
            )

            if selected is None:
                raise RemoteParserError(
                    f"MinerU result for {file_name} "
                    "does not contain final Markdown."
                )

            # 同时限制 ZIP 内文件的解压后大小，避免压缩炸弹占满内存。
            if selected.file_size > max_markdown_bytes:
                raise DocumentTooLargeError(
                    f"MinerU Markdown result for {file_name} exceeds "
                    f"{max_markdown_bytes} bytes."
                )

            raw = archive.read(selected)

            content_lists = [
                info
                for info in archive.infolist()
                if (
                    not info.is_dir()
                    and PurePosixPath(info.filename).name.lower().endswith(
                        "_content_list.json"
                    )
                )
            ]
            content_list_raw = None
            if (
                    len(content_lists) == 1
                    and content_lists[0].file_size <= max_markdown_bytes
            ):
                try:
                    content_list_raw = archive.read(content_lists[0])
                except Exception:
                    pass

    except (RemoteParserError, DocumentTooLargeError):
        raise
    except zipfile.BadZipFile as exc:
        raise RemoteParserError(
            f"MinerU result for {file_name} is not a valid ZIP archive."
        ) from exc
    except Exception as exc:
        raise RemoteParserError(
            f"Failed to read MinerU result for {file_name}."
        ) from exc

    markdown = decode_text(
        raw,
        file_name=PurePosixPath(selected.filename).name,
    ).strip()
    if content_list_raw is None:
        return markdown

    try:
        content_list = json.loads(
            decode_text(
                content_list_raw,
                file_name=PurePosixPath(content_lists[0].filename).name,
            )
        )
    except Exception:
        return markdown

    return insert_page_markers(markdown, content_list)


def _http_timeout(total_seconds: float) -> httpx.Timeout:
    return httpx.Timeout(
        timeout=total_seconds,
        connect=min(10.0, total_seconds),
        pool=min(10.0, total_seconds),
    )
