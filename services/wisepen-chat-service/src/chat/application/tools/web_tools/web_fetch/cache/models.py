from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.web_tools.web_fetch.models import WebFetchResult


@dataclass(frozen=True, slots=True)
class CachedWebFetchPage:
    """命中 URL 缓存的网页结果，保留 crawl 抽链需要的 raw_html。"""

    result: WebFetchResult
    raw_html: str | None
