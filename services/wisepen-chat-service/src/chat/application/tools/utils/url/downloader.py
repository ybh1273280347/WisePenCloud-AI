from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from dataclasses import dataclass

import httpx

from chat.application.tools.utils.file_type_detect import FileType, detect_file_type_from_bytes
from .filename import filename_from_url
from .security import UrlSecurityError, validate_public_http_url_async

_DEFAULT_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_SNIFF_BUFFER_BYTES = 32_768
_STREAM_CHUNK_SIZE = 65_536
_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


class UrlDownloadError(RuntimeError):
    """URL 下载基础异常。"""

    def __init__(self, *, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class UrlDownloadNetworkError(UrlDownloadError):
    """网络层失败。"""


class UrlDownloadHttpError(UrlDownloadError):
    """HTTP 层失败。"""


class UrlDownloadUnsupportedUrlError(UrlDownloadError):
    """不支持或不安全的 URL。"""


@dataclass(frozen=True, slots=True)
class DownloadedUrl:
    """URL 下载结果：非 HTML 内容已经落到临时文件。"""

    source_url: str
    downloader: str
    status_code: int
    headers: dict[str, str]
    file_type: FileType
    file_path: str
    content_type: str | None = None

    @property
    def file_label(self) -> str:
        return self.file_type.label


async def download_url(
        url: str,
        *,
        http_client: httpx.AsyncClient,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int = 52_428_800,
) -> DownloadedUrl:
    """下载公开 http(s) 非 HTML URL 到临时文件。"""
    try:
        source_url = await validate_public_http_url_async(url)
    except UrlSecurityError as exc:
        raise UrlDownloadUnsupportedUrlError(url=url, reason=str(exc)) from exc

    try:
        async with http_client.stream(
                "GET",
                source_url,
                headers=headers if headers is not None else _DEFAULT_DOWNLOAD_HEADERS,
                follow_redirects=False,
        ) as response:
            if 300 <= response.status_code < 400:
                raise UrlDownloadUnsupportedUrlError(
                    url=source_url,
                    reason="redirect_not_allowed",
                )

            if response.status_code >= 400:
                raise UrlDownloadHttpError(
                    url=source_url,
                    reason=f"http {response.status_code}",
                )

            stream = response.aiter_bytes(chunk_size=_STREAM_CHUNK_SIZE)
            first_chunk = await anext(stream, b"")
            sniff_buffer = first_chunk[:_SNIFF_BUFFER_BYTES]

            file_type = detect_file_type_from_bytes(
                sniff_buffer,
                fallback_name=filename_from_url(source_url),
            )
            content_type = response.headers.get("content-type")
            media_type = (content_type or "").partition(";")[0].strip().lower()

            if file_type.label == "html" or media_type in _HTML_CONTENT_TYPES:
                raise UrlDownloadUnsupportedUrlError(
                    url=source_url,
                    reason="url_resolved_to_html",
                )

            file_path = await _write_stream_to_temp_file(
                stream,
                initial_bytes=first_chunk,
                suffix=file_type.label,
                max_bytes=max_response_bytes,
                url=source_url,
            )

            return DownloadedUrl(
                source_url=source_url,
                downloader="url_downloader",
                status_code=response.status_code,
                headers=dict(response.headers),
                content_type=content_type,
                file_type=file_type,
                file_path=file_path,
            )

    except UrlDownloadError:
        raise
    except httpx.TimeoutException as exc:
        raise UrlDownloadNetworkError(
            url=source_url,
            reason=f"timeout: {exc}",
        ) from exc
    except httpx.NetworkError as exc:
        raise UrlDownloadNetworkError(
            url=source_url,
            reason=f"network: {exc}",
        ) from exc
    except httpx.HTTPError as exc:
        raise UrlDownloadNetworkError(
            url=source_url,
            reason=f"http: {exc}",
        ) from exc
    except Exception as exc:
        raise UrlDownloadNetworkError(
            url=source_url,
            reason=f"unexpected: {exc}",
        ) from exc


async def _write_stream_to_temp_file(
        stream: AsyncIterator[bytes],
        *,
        initial_bytes: bytes,
        suffix: str | None,
        max_bytes: int,
        url: str,
) -> str:
    written = len(initial_bytes)
    if written > max_bytes:
        raise UrlDownloadNetworkError(
            url=url,
            reason=f"response exceeded max bytes {max_bytes}",
        )

    fd, tmp_path = tempfile.mkstemp(
        prefix="tool_download_",
        suffix=f".{suffix}" if suffix else "",
    )

    try:
        with os.fdopen(fd, "wb") as file:
            file.write(initial_bytes)

            async for chunk in stream:
                written += len(chunk)
                if written > max_bytes:
                    raise UrlDownloadNetworkError(
                        url=url,
                        reason=f"response exceeded max bytes {max_bytes}",
                    )
                file.write(chunk)

        return tmp_path

    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_path)
        raise
