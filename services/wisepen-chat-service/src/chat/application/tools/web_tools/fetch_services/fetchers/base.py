from __future__ import annotations

from typing import Protocol

from ..core.models import RawFetchOutput


class WebFetcher(Protocol):
    @property
    def name(self) -> str:
        ...

    async def fetch(self, url: str) -> RawFetchOutput:
        ...
