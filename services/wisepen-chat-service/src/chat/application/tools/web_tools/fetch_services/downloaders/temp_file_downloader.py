from __future__ import annotations

import httpx

from chat.application.tools.utils.url import (
    UrlDownloadError,
    UrlDownloadHttpError,
    UrlDownloadNetworkError,
    UrlDownloadUnsupportedUrlError,
    download_url,
)
from ..core.errors import (
    UrlFetchHttpError,
    UrlFetchNetworkError,
    UrlFetchUnsupportedUrlError,
)
from ..core.models import RawFetchOutput


class TempFileDownloader:
    """临时文件下载器。只处理非 HTML 文件，HTML 交回页面抓取链路。"""

    __slots__ = ("_http", "_max_response_bytes")

    def __init__(
            self,
            *,
            http_client: httpx.AsyncClient,
            max_response_bytes: int = 52_428_800,
    ) -> None:
        self._http = http_client
        self._max_response_bytes = max_response_bytes

    async def download(self, url: str) -> RawFetchOutput:
        try:
            downloaded_url = await download_url(
                url,
                http_client=self._http,
                max_response_bytes=self._max_response_bytes,
            )
            return RawFetchOutput(
                source_url=downloaded_url.source_url,
                fetcher="temp_file_downloader",
                status_code=downloaded_url.status_code,
                content_type=downloaded_url.content_type,
                headers=downloaded_url.headers,
                file_path=downloaded_url.file_path,
                file_label=downloaded_url.file_type.label,
            )

        except (UrlFetchHttpError, UrlFetchNetworkError, UrlFetchUnsupportedUrlError):
            raise
        except UrlDownloadHttpError as exc:
            raise UrlFetchHttpError(url=exc.url, reason=exc.reason) from exc
        except UrlDownloadUnsupportedUrlError as exc:
            raise UrlFetchUnsupportedUrlError(url=exc.url, reason=exc.reason) from exc
        except UrlDownloadNetworkError as exc:
            raise UrlFetchNetworkError(url=exc.url, reason=exc.reason) from exc
        except UrlDownloadError as exc:
            raise UrlFetchNetworkError(url=exc.url, reason=exc.reason) from exc
        except httpx.TimeoutException as exc:
            raise UrlFetchNetworkError(url=url, reason=f"timeout: {exc}") from exc
        except httpx.NetworkError as exc:
            raise UrlFetchNetworkError(url=url, reason=f"network: {exc}") from exc
        except httpx.HTTPError as exc:
            raise UrlFetchNetworkError(url=url, reason=f"http: {exc}") from exc
        except Exception as exc:
            raise UrlFetchNetworkError(url=url, reason=f"unexpected: {exc}") from exc
