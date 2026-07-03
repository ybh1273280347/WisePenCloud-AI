from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx

from chat.application.tools.utils.file_type_detect import FileType, detect_file_type_from_bytes
from .filename import filename_from_url
from .security import UrlSecurityError, validate_public_http_url

_DEFAULT_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_DEFAULT_HTML_FETCH_HEADERS = {
    **_DEFAULT_FETCH_HEADERS,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}

_SNIFF_BUFFER_BYTES = 32_768
_STREAM_CHUNK_SIZE = 65_536
_MAX_REDIRECTS = 10


class UrlFetcherError(RuntimeError):
    """URL 抓取基础异常。"""

    def __init__(self, *, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.url}: {self.reason}"


class UrlFetcherNetworkError(UrlFetcherError):
    """网络层失败。"""


class UrlFetcherHttpError(UrlFetcherError):
    """HTTP 层失败。"""


class UrlFetcherUnsupportedUrlError(UrlFetcherError):
    """不支持或不安全的 URL。"""


@dataclass(frozen=True, slots=True)
class FetchedUrl:
    """URL 抓取结果：HTML 保存在 body，非 HTML 保存在 file_path。"""

    source_url: str
    fetcher: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    file_type: FileType
    charset_encoding: str | None
    content_type: str | None = None
    body: bytes | None = None
    file_path: str | None = None

    @property
    def file_label(self) -> str:
        return self.file_type.label


async def fetch_url(
        url: str,
        *,
        http_client: httpx.AsyncClient,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int = 52_428_800,
        allow_html: bool = True,
) -> FetchedUrl:
    """抓取公开 http(s) URL，HTML 返回字节正文，非 HTML 写入临时文件。"""
    try:
        async with _open_sniffed_url_response(
                url,
                http_client=http_client,
                headers=headers or (
                        _DEFAULT_HTML_FETCH_HEADERS
                        if allow_html
                        else _DEFAULT_FETCH_HEADERS
                ),
        ) as response:
            budget = max_response_bytes - len(response.sniff_buffer)
            if budget < 0:
                raise UrlFetcherNetworkError(
                    url=url,
                    reason=f"response exceeded max bytes {max_response_bytes}",
                )

            content_type_prefix = (response.content_type or "").split(";", maxsplit=1)[0].strip().lower()
            is_html = response.file_type.label == "html" or content_type_prefix in {
                "text/html",
                "application/xhtml+xml",
            }

            if is_html:
                if not allow_html:
                    raise UrlFetcherUnsupportedUrlError(
                        url=url,
                        reason="url_resolved_to_html",
                    )
                return FetchedUrl(
                    source_url=url,
                    fetcher="httpx",
                    final_url=response.final_url,
                    status_code=response.status_code,
                    content_type=response.content_type,
                    headers=response.headers,
                    file_type=response.file_type,
                    charset_encoding=response.charset_encoding,
                    body=response.sniff_buffer + b"".join([
                        chunk
                        async for chunk in _bounded_stream(response.stream, budget, url)
                    ]),
                )

            return FetchedUrl(
                source_url=url,
                fetcher="httpx",
                final_url=response.final_url,
                status_code=response.status_code,
                content_type=response.content_type,
                headers=response.headers,
                file_type=response.file_type,
                charset_encoding=response.charset_encoding,
                file_path=await _write_stream_to_temp_file(
                    _bounded_stream(response.stream, budget, url),
                    initial_bytes=response.sniff_buffer,
                    suffix=response.file_type.label,
                ),
            )

    except (UrlFetcherHttpError, UrlFetcherNetworkError, UrlFetcherUnsupportedUrlError):
        raise
    except Exception as exc:
        raise UrlFetcherNetworkError(url=url, reason=f"unexpected: {exc}") from exc


@dataclass(frozen=True, slots=True)
class _SniffedUrlResponse:
    final_url: str
    status_code: int
    content_type: str | None
    headers: dict[str, str]
    sniff_buffer: bytes
    file_type: FileType
    charset_encoding: str | None
    stream: AsyncIterator[bytes]


@asynccontextmanager
async def _open_sniffed_url_response(
        url: str,
        *,
        http_client: httpx.AsyncClient,
        headers: Mapping[str, str] | None = None,
) -> AsyncGenerator[_SniffedUrlResponse, None]:
    """打开 http(s) 响应流并完成前缀嗅探，调用方负责消费剩余 stream。"""
    current_url = _validate_fetch_url(url)
    redirects = 0

    while True:
        try:
            async with http_client.stream(
                    "GET",
                    current_url,
                    headers=dict(headers or _DEFAULT_FETCH_HEADERS),
                    follow_redirects=False,
            ) as response:
                if 300 <= response.status_code < 400:
                    redirects += 1
                    if redirects > _MAX_REDIRECTS:
                        raise UrlFetcherNetworkError(url=url, reason="too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UrlFetcherHttpError(url=current_url, reason=f"http {response.status_code}")
                    current_url = _validate_fetch_url(urljoin(str(response.url), location))
                    continue

                if response.status_code >= 400:
                    raise UrlFetcherHttpError(url=current_url, reason=f"http {response.status_code}")

                final_url = _validate_fetch_url(str(response.url))
                stream = response.aiter_bytes(chunk_size=_STREAM_CHUNK_SIZE)
                sniff_buffer = await _read_stream_prefix(stream, _SNIFF_BUFFER_BYTES)
                yield _SniffedUrlResponse(
                    final_url=final_url,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type"),
                    headers=dict(response.headers),
                    sniff_buffer=sniff_buffer,
                    file_type=detect_file_type_from_bytes(
                        sniff_buffer,
                        fallback_name=filename_from_url(final_url),
                    ),
                    charset_encoding=response.charset_encoding,
                    stream=stream,
                )
                return

        except (UrlFetcherHttpError, UrlFetcherNetworkError, UrlFetcherUnsupportedUrlError):
            raise
        except httpx.TimeoutException as exc:
            raise UrlFetcherNetworkError(url=current_url, reason=f"timeout: {exc}") from exc
        except httpx.NetworkError as exc:
            raise UrlFetcherNetworkError(url=current_url, reason=f"network: {exc}") from exc
        except httpx.HTTPError as exc:
            raise UrlFetcherNetworkError(url=current_url, reason=f"http: {exc}") from exc
        except Exception as exc:
            raise UrlFetcherNetworkError(url=current_url, reason=f"unexpected: {exc}") from exc


def _validate_fetch_url(url: str) -> str:
    try:
        return validate_public_http_url(url)
    except UrlSecurityError as exc:
        raise UrlFetcherUnsupportedUrlError(url=url, reason=str(exc)) from exc


async def _write_stream_to_temp_file(
        stream: AsyncIterator[bytes],
        *,
        initial_bytes: bytes = b"",
        suffix: str | None = None,
) -> str:
    fd, tmp_path = tempfile.mkstemp(prefix="tool_fetch_", suffix=f".{suffix}" if suffix else "")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(initial_bytes)
            async for chunk in stream:
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        return tmp_path
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink(missing_ok=True)
        raise


async def _read_stream_prefix(
        stream: AsyncIterator[bytes],
        max_bytes: int,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in stream:
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_bytes:
            break
    return b"".join(chunks)[:max_bytes]


async def _bounded_stream(
        stream: AsyncIterator[bytes],
        budget: int,
        url: str,
) -> AsyncGenerator[bytes, None]:
    """逐块转发并计数，超出 budget 立即抛错，避免超大响应被完整读入内存后才发现超限。"""
    remaining = budget
    async for chunk in stream:
        remaining -= len(chunk)
        if remaining < 0:
            raise UrlFetcherNetworkError(url=url, reason=f"response exceeded max bytes {budget}")
        yield chunk
