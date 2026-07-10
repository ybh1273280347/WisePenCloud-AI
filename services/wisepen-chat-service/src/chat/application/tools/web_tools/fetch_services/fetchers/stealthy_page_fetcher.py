from __future__ import annotations

from typing import Any

from ..core.errors import (
    UrlFetchHttpError,
    UrlFetchNetworkError,
    UrlFetchUnsupportedUrlError,
)
from ..core.models import RawFetchOutput
from .._utils.page_url import validate_page_url
from .._utils.page_response import build_raw_html_output

_DEFAULT_TIMEOUT_MS = 30_000


class StealthyPageFetcher:
    """浏览器 HTML 页面抓取器。session 生命周期由容器管理。"""

    __slots__ = ("_max_response_bytes", "_session", "_timeout_ms")

    def __init__(
            self,
            *,
            session: Any,
            timeout_ms: int = _DEFAULT_TIMEOUT_MS,
            max_response_bytes: int = 52_428_800,
    ) -> None:
        self._session = session
        self._timeout_ms = timeout_ms
        self._max_response_bytes = max_response_bytes

    @property
    def name(self) -> str:
        return "stealthy_page"

    async def fetch(self, url: str) -> RawFetchOutput:
        try:
            url = validate_page_url(url)
            response = await self._session.fetch(
                url,
                timeout=self._timeout_ms,
                disable_resources=True,
                block_ads=True,
                network_idle=False,
                load_dom=True,
                wait=0,
                solve_cloudflare=False,
            )
            return build_raw_html_output(
                response,
                source_url=url,
                fetcher=self.name,
                max_response_bytes=self._max_response_bytes,
            )
        except (UrlFetchHttpError, UrlFetchNetworkError, UrlFetchUnsupportedUrlError):
            raise
        except Exception as exc:
            raise UrlFetchNetworkError(
                url=url,
                reason=f"stealthy page fetch failed: {exc}",
            ) from exc
