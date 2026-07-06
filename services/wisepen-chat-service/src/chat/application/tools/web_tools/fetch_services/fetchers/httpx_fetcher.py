from __future__ import annotations

import httpx

from chat.application.tools.utils.url import (
    UrlFetcherError,
    UrlFetcherHttpError,
    UrlFetcherNetworkError,
    UrlFetcherUnsupportedUrlError,
    fetch_url,
)
from .._utils import decode_bytes
from ..core.errors import (
    UrlFetchHttpError,
    UrlFetchNetworkError,
    UrlFetchUnsupportedUrlError,
)
from ..core.models import RawFetchOutput


class HttpxFetcher:
    """web_fetch 的 httpx 抓取器，HTML 返回文本，非 HTML 写入临时文件。"""

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
        try:
            content = await fetch_url(
                url,
                http_client=self._http,
                max_response_bytes=self._max_response_bytes,
                allow_html=True,
            )
            base = dict(
                source_url=url,
                fetcher=self.name,
                final_url=content.final_url,
                status_code=content.status_code,
                content_type=content.content_type,
                headers=content.headers,
            )

            if content.body is not None:
                return RawFetchOutput(
                    **base,
                    raw_html=decode_bytes(content.body, content.charset_encoding),
                )

            return RawFetchOutput(
                **base,
                file_path=content.file_path,
                file_label=content.file_type.label,
            )

        except (UrlFetchHttpError, UrlFetchNetworkError, UrlFetchUnsupportedUrlError):
            raise
        except UrlFetcherHttpError as exc:
            raise UrlFetchHttpError(url=exc.url, reason=exc.reason) from exc
        except UrlFetcherUnsupportedUrlError as exc:
            raise UrlFetchUnsupportedUrlError(url=exc.url, reason=exc.reason) from exc
        except UrlFetcherNetworkError as exc:
            raise UrlFetchNetworkError(url=exc.url, reason=exc.reason) from exc
        except UrlFetcherError as exc:
            raise UrlFetchNetworkError(url=exc.url, reason=exc.reason) from exc
        except httpx.TimeoutException as exc:
            raise UrlFetchNetworkError(url=url, reason=f"timeout: {exc}") from exc
        except httpx.NetworkError as exc:
            raise UrlFetchNetworkError(url=url, reason=f"network: {exc}") from exc
        except httpx.HTTPError as exc:
            raise UrlFetchNetworkError(url=url, reason=f"http: {exc}") from exc
        except Exception as exc:
            raise UrlFetchNetworkError(url=url, reason=f"unexpected: {exc}") from exc
