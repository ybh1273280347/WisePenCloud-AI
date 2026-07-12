from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from chat.application.tools.search_tools.web_search.providers.models import SearchCapability, SearchProviderName
from chat.application.tools.search_tools.web_search.searchers import ProviderSearcher


class WebSearchSourceKind(StrEnum):
    """运行时搜索源类型，表示密钥归属和缓存域。"""

    PLATFORM_DEFAULT = "platform_default"
    CUSTOM = "custom"


@runtime_checkable
class WebSearchRuntimeSource(Protocol):
    kind: WebSearchSourceKind
    provider: SearchProviderName | None
    source_id: str
    searcher: ProviderSearcher
    api_key: str | None

    @property
    def capability(self) -> SearchCapability: ...


@dataclass(frozen=True, slots=True)
class PlatformDefaultSearchSource:
    """平台默认搜索源，对外只暴露 platform_default。"""

    searcher: ProviderSearcher
    kind: WebSearchSourceKind = WebSearchSourceKind.PLATFORM_DEFAULT
    provider: SearchProviderName | None = None
    source_id: str = "platform_default"
    api_key: str | None = None

    @property
    def capability(self) -> SearchCapability:
        return SearchCapability(web=True, academic=False)


@dataclass(frozen=True, slots=True)
class CustomSearchSource:
    """用户自定义搜索源，使用用户上传的 API key。"""

    provider: SearchProviderName
    source_id: str
    searcher: ProviderSearcher
    api_key: str
    kind: WebSearchSourceKind = WebSearchSourceKind.CUSTOM

    @property
    def capability(self) -> SearchCapability:
        return self.provider.capability
