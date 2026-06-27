from __future__ import annotations

from collections.abc import Mapping

from chat.application.tools.web_tools.search_services.providers.models import SearchProviderName
from chat.application.tools.web_tools.search_services.searchers import ProviderSearcher
from ..search import WebSearchCustomSource, WebSearchResult, execute_provider_search


class WebSearchService:
    """Web search 编排服务。

    service 不读取用户配置、不解密凭证；custom 配置必须先固化到 tool context。
    """

    def __init__(
        self,
        *,
        platform_searchers: Mapping[SearchProviderName, ProviderSearcher],
    ) -> None:
        self._platform_searchers = dict(platform_searchers)

    async def search(
        self,
        *,
        query: str,
        max_results: int = 10,
        custom_source: WebSearchCustomSource | None = None,
        platform_provider: SearchProviderName = SearchProviderName.FOUGET_DDG,
    ) -> WebSearchResult:
        return await execute_provider_search(
            query=query,
            custom_source=custom_source,
            platform_provider=platform_provider,
            platform_searchers=self._platform_searchers,
            search_once=lambda searcher: searcher.search_web(
                query=query,
                max_results=max_results,
            ),
        )
