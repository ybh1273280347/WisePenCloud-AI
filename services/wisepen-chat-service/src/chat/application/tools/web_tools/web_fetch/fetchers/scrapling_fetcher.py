from __future__ import annotations

from scrapling.fetchers import StealthyFetcher

from chat.application.tools.utils.url import UrlSecurityError, validate_public_http_url
from common.logger import warn
from .._utils import decode_bytes
from ..errors import (
    UrlFetchHttpError,
    UrlFetchNetworkError,
    UrlFetchUnsupportedUrlError,
)
from ..models import RawFetchOutput

_DEFAULT_TIMEOUT_MS = 30_000


class ScraplingFetcher:
    """Scrapling StealthyFetcher 动态抓取器。只处理 HTML（非 HTML 由 httpx 拦截）。"""

    __slots__ = ("_timeout_ms", "_max_response_bytes")

    def __init__(
            self,
            *,
            timeout_ms: int = _DEFAULT_TIMEOUT_MS,
            max_response_bytes: int = 52_428_800,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._max_response_bytes = max_response_bytes

    @property
    def name(self) -> str:
        return "scrapling"

    async def fetch(self, url: str) -> RawFetchOutput:
        try:
            url = validate_public_http_url(url.strip())
        except UrlSecurityError as exc:
            raise UrlFetchUnsupportedUrlError(
                url=url,
                reason=str(exc),
            ) from exc

        try:
            response = await StealthyFetcher.async_fetch(
                url,
                headless=True,
                network_idle=True,
                timeout=self._timeout_ms,
            )
        except Exception as exc:
            raise UrlFetchNetworkError(
                url=url,
                reason=f"scrapling fetch failed: {exc}",
            ) from exc

        # Response 字段：status, headers, url, body, encoding, history
        status: int = response.status
        if status >= 400:
            raise UrlFetchHttpError(url=url, reason=f"http {status}")

        raw_bytes: bytes = response.body or b""
        if not raw_bytes:
            raise UrlFetchNetworkError(url=url, reason="empty response body")

        if len(raw_bytes) > self._max_response_bytes:
            warn(
                "web_fetch scrapling response exceeded max bytes",
                url=url,
                max_bytes=self._max_response_bytes,
            )
            raise UrlFetchNetworkError(
                url=url,
                reason=f"response exceeded max bytes {self._max_response_bytes}",
            )

        headers: dict[str, str] = dict(response.headers)
        content_type = headers.get("content-type")
        try:
            final_url = validate_public_http_url(str(response.url))
        except UrlSecurityError as exc:
            raise UrlFetchUnsupportedUrlError(url=str(response.url), reason=str(exc)) from exc
        encoding: str = response.encoding

        raw_html = decode_bytes(raw_bytes, encoding)

        return RawFetchOutput(
            source_url=url,
            fetcher=self.name,
            final_url=final_url,
            status_code=status,
            content_type=content_type,
            headers=headers,
            raw_html=raw_html,
        )
