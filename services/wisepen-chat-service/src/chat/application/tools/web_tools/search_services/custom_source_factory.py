from __future__ import annotations

from dataclasses import dataclass

import httpx

from .errors import (
    WebSearchCustomApiKeyInvalid,
    WebSearchCustomApiKeyMissing,
)
from .providers.models import SearchProviderName
from .runtime_context import WebSearchRuntimeConfig
from .searchers import (
    AnySearchSearcher,
    BaiduQianfanSearcher,
    BaseProviderSearcher,
    ExaSearcher,
    SearchProviderConfig,
    TavilySearcher,
)
from .services.search import WebSearchCustomSource


@dataclass(frozen=True, slots=True)
class WebSearchCustomSourceFactory:
    """按已固化到 context 的运行期配置构造 custom 搜索源。"""

    http_client: httpx.AsyncClient
    exa_base_url: str
    tavily_base_url: str
    anysearch_base_url: str
    baidu_qianfan_base_url: str

    def build(self, config: WebSearchRuntimeConfig) -> WebSearchCustomSource:
        if not config.api_key:
            raise WebSearchCustomApiKeyMissing(
                provider=config.provider,
                reason="不存在 api key",
            )
        provider_config = SearchProviderConfig(
            base_url=self._base_url(config.provider),
            api_key=config.api_key,
            source_id=config.source_id,
        )
        searcher = self._provider_searcher(config.provider, provider_config)
        return WebSearchCustomSource(
            provider=config.provider,
            searcher=searcher,
            api_key=config.api_key,
        )

    def _provider_searcher(
        self,
        provider: SearchProviderName,
        config: SearchProviderConfig,
    ) -> BaseProviderSearcher:
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
            reason="该 provider 不支持 custom 搜索",
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
            reason="该 provider 不支持 custom 搜索",
        )
