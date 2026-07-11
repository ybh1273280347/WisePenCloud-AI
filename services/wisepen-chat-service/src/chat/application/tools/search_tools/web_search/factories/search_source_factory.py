from __future__ import annotations

from dataclasses import dataclass

import httpx

from chat.application.tools.search_tools.web_search.core.errors import (
    WebSearchCustomApiKeyInvalid,
    WebSearchInternalError,
)
from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import (
    CustomSearchSource,
    PlatformDefaultSearchSource,
    PlatformMemberSearchSource,
    WebSearchSourceKind,
)
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName
from chat.application.tools.search_tools.web_search.searchers import (
    AnySearchSearcher,
    BaiduQianfanSearcher,
    BaseProviderSearcher,
    ExaSearcher,
    PlatformDefaultSearcher,
    SearchProviderConfig,
    TavilySearcher,
)


@dataclass(frozen=True, slots=True)
class SearchSourceFactory:
    """从运行时配置统一构造平台或 custom 搜索源。"""

    http_client: httpx.AsyncClient
    platform_default_searcher: PlatformDefaultSearcher
    exa_base_url: str
    tavily_base_url: str
    anysearch_base_url: str
    baidu_qianfan_base_url: str

    def build(self, config: WebSearchRuntimeConfig) -> PlatformDefaultSearchSource | PlatformMemberSearchSource | CustomSearchSource:
        if config.source_kind == WebSearchSourceKind.PLATFORM_DEFAULT:
            return PlatformDefaultSearchSource(searcher=self.platform_default_searcher)

        if config.provider is None or not config.api_key:
            raise WebSearchInternalError(
                provider=config.provider,
                reason="搜索源缺少 provider 或 API key",
            )

        searcher = self._build_provider_searcher(
            provider=config.provider,
            api_key=config.api_key,
            source_id=config.source_id,
        )
        if config.source_kind == WebSearchSourceKind.PLATFORM_MEMBER:
            return PlatformMemberSearchSource(
                provider=config.provider,
                source_id=config.source_id,
                searcher=searcher,
                api_key=config.api_key,
            )
        if config.source_kind == WebSearchSourceKind.CUSTOM:
            return CustomSearchSource(
                provider=config.provider,
                source_id=config.source_id,
                searcher=searcher,
                api_key=config.api_key,
            )
        raise WebSearchInternalError(
            provider=config.provider,
            reason="未知搜索源类型",
        )

    def _build_provider_searcher(
            self,
            *,
            provider: SearchProviderName,
            api_key: str,
            source_id: str,
    ) -> BaseProviderSearcher:
        config = SearchProviderConfig(
            base_url=self._base_url(provider),
            api_key=api_key,
            source_id=source_id,
        )
        if provider == SearchProviderName.EXA:
            return ExaSearcher(http_client=self.http_client, config=config)
        if provider == SearchProviderName.TAVILY:
            return TavilySearcher(http_client=self.http_client, config=config)
        if provider == SearchProviderName.ANYSEARCH:
            return AnySearchSearcher(http_client=self.http_client, config=config)
        if provider == SearchProviderName.BAIDU_QIANFAN:
            return BaiduQianfanSearcher(http_client=self.http_client, config=config)
        raise WebSearchCustomApiKeyInvalid(
            provider=provider,
            reason="该 provider 不支持 API key 搜索源",
        )

    def _base_url(self, provider: SearchProviderName) -> str:
        if provider == SearchProviderName.EXA:
            return self.exa_base_url
        if provider == SearchProviderName.TAVILY:
            return self.tavily_base_url
        if provider == SearchProviderName.ANYSEARCH:
            return self.anysearch_base_url
        if provider == SearchProviderName.BAIDU_QIANFAN:
            return self.baidu_qianfan_base_url
        raise WebSearchCustomApiKeyInvalid(
            provider=provider,
            reason="该 provider 不支持 API key 搜索源",
        )
