from __future__ import annotations

from chat.application.tools.web_tools.search_services.core.sources import WebSearchRuntimeSource
from chat.application.tools.web_tools.search_services.pipeline.search_executor import (
    WebSearchResult,
    execute_provider_search,
)


class WebSearchService:
    """Web search 编排服务。

    service 不读取用户配置、不解密凭证；搜索源必须先固化到 source 对象。
    """

    async def search(
            self,
            *,
            query: str,
            max_results: int = 10,
            source: WebSearchRuntimeSource,
    ) -> WebSearchResult:
        return await execute_provider_search(
            query=query,
            source=source,
            search_once=lambda searcher: searcher.search_web(
                query=query,
                max_results=max_results,
            ),
        )
