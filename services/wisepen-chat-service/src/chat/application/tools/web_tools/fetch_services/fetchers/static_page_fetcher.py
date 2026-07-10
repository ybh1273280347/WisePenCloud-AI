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


class StaticPageFetcher:
    """静态 HTML 页面抓取器。session 生命周期由容器管理。"""

    __slots__ = ("_max_response_bytes", "_session")

    def __init__(
            self,
            *,
            session: Any,
            max_response_bytes: int = 52_428_800,
    ) -> None:
        self._session = session
        self._max_response_bytes = max_response_bytes

    @property
    def name(self) -> str:
        return "static_page"

    async def fetch(self, url: str) -> RawFetchOutput:
        try:
            url = validate_page_url(url)
            response = await self._session.get(url, follow_redirects=False)
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
                reason=f"static page fetch failed: {exc}",
            ) from exc
