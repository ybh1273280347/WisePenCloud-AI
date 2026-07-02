from __future__ import annotations

import contextlib
import os
import re
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx
from charset_normalizer import from_bytes as detect_encoding

from chat.application.tools.utils.file_type_detect import detect_file_type_from_bytes
from common.logger import warn

_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_SNIFF_BUFFER_BYTES = 32_768  # 32 KiB
_STREAM_CHUNK_SIZE = 65_536   # 64 KiB


class UrlFetchError(RuntimeError):
    """URL 抓取基础异常。"""

    def __init__(self, *, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.url}: {self.reason}"


class UrlFetchNetworkError(UrlFetchError):
    """网络层失败。"""


class UrlFetchHttpError(UrlFetchError):
    """HTTP 层失败。"""


class UrlFetchUnsupportedUrlError(UrlFetchError):
    """不支持的 URL 协议或安全策略拒绝。"""


@dataclass(frozen=True, slots=True)
class RawFetchOutput:
    """URL 抓取原始结果：HTML 文本或非 HTML 临时文件路径。"""

    source_url: str
    fetcher: str
    final_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    raw_html: str | None = None
    file_path: str | None = None
    file_label: str | None = None


class BaseFetcher(Protocol):
    @property
    def name(self) -> str:
        ...

    async def fetch(self, url: str) -> RawFetchOutput:
        ...


class HttpxFetcher:
    """httpx URL 抓取器，HTML 返回文本，非 HTML 写入临时文件。"""

    __slots__ = ("_http", "_max_response_bytes")

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        max_response_bytes: int = 52_428_800,
    ) -> None:
        self._http = http_client
        self._max_response_bytes = max_response_bytes

    @property
    def name(self) -> str:
        return "httpx"

    async def fetch(self, url: str) -> RawFetchOutput:
        if not _URL_SCHEME_RE.match(url.strip()):
            raise UrlFetchUnsupportedUrlError(
                url=url,
                reason="unsupported url scheme, only http/https allowed",
            )

        try:
            async with self._http.stream(
                "GET",
                url,
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
            ) as response:
                if response.status_code >= 400:
                    raise UrlFetchHttpError(url=url, reason=f"http {response.status_code}")

                content_type = response.headers.get("content-type")
                final_url = str(response.url)
                headers = dict(response.headers)

                stream = response.aiter_bytes(chunk_size=_STREAM_CHUNK_SIZE)
                sniff_buffer = await _read_sniff_from_stream(stream, _SNIFF_BUFFER_BYTES)
                file_type = detect_file_type_from_bytes(
                    sniff_buffer,
                    fallback_name=filename_from_url(final_url),
                )

                budget = self._max_response_bytes - len(sniff_buffer)
                base = dict(
                    source_url=url,
                    fetcher=self.name,
                    final_url=final_url,
                    status_code=response.status_code,
                    content_type=content_type,
                    headers=headers,
                )

                if file_type.label == "html":
                    remaining = await _drain_bounded(stream, budget, url)
                    return RawFetchOutput(
                        **base,
                        raw_html=decode_bytes(sniff_buffer + remaining, response.charset_encoding),
                    )

                file_path = await _write_to_temp_file(
                    stream,
                    sniff_buffer,
                    budget,
                    url,
                    file_type.label,
                )
                return RawFetchOutput(
                    **base,
                    file_path=file_path,
                    file_label=file_type.label,
                )

        except (UrlFetchHttpError, UrlFetchNetworkError, UrlFetchUnsupportedUrlError):
            raise
        except httpx.TimeoutException as exc:
            raise UrlFetchNetworkError(url=url, reason=f"timeout: {exc}") from exc
        except httpx.NetworkError as exc:
            raise UrlFetchNetworkError(url=url, reason=f"network: {exc}") from exc
        except httpx.HTTPError as exc:
            raise UrlFetchNetworkError(url=url, reason=f"http: {exc}") from exc
        except Exception as exc:
            raise UrlFetchNetworkError(url=url, reason=f"unexpected: {exc}") from exc


def decode_bytes(raw: bytes, declared_encoding: str | None) -> str:
    """按声明编码、探测编码、UTF-8 的顺序解码。"""
    if declared_encoding:
        try:
            return raw.decode(declared_encoding, errors="replace")
        except LookupError:
            pass

    result = detect_encoding(
        raw,
        cp_isolation=["utf-8", "gbk", "big5", "shift_jis", "euc_kr"],
    ).best()
    return str(result) if result is not None else raw.decode("utf-8", errors="replace")


def filename_from_url(url: str) -> str | None:
    """从 URL 提取文件名，用于 fallback 文件类型检测或展示名。"""
    try:
        path = urlparse(url).path
        name = Path(path).name
        return name if name else None
    except Exception:
        return None


async def _read_sniff_from_stream(
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
    remaining = budget
    async for chunk in stream:
        remaining -= len(chunk)
        if remaining < 0:
            warn("tool url fetch response exceeded max bytes", url=url, max_bytes=budget)
            raise UrlFetchNetworkError(url=url, reason=f"response exceeded max bytes {budget}")
        yield chunk


async def _drain_bounded(
    stream: AsyncIterator[bytes],
    budget: int,
    url: str,
) -> bytes:
    return b"".join([chunk async for chunk in _bounded_stream(stream, budget, url)])


async def _write_to_temp_file(
    stream: AsyncIterator[bytes],
    sniff_buffer: bytes,
    budget: int,
    url: str,
    label: str,
) -> str:
    fd, tmp_path = tempfile.mkstemp(prefix="tool_fetch_", suffix=f".{label}" if label else "")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(sniff_buffer)
            async for chunk in _bounded_stream(stream, budget, url):
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        return tmp_path
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink(missing_ok=True)
        raise
