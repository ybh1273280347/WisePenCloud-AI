from __future__ import annotations

from .base import WebFetcher
from .httpx_fetcher import HttpxFetcher
from .scrapling_fetcher import ScraplingFetcher

__all__ = [
    "HttpxFetcher",
    "ScraplingFetcher",
    "WebFetcher",
]
