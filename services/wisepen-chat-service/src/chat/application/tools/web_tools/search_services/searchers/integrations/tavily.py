from __future__ import annotations

import httpx

from chat.application.tools.web_tools.search_services.providers.models import SearchProviderName
from chat.application.tools.web_tools.search_services.providers.tavily import (
    TavilySearchRequest,
    map_tavily_response,
)
from chat.application.tools.web_tools.search_services.searchers.base import (
    BaseProviderSearcher,
    SearchProviderConfig,
    SearchProviderCredentialError,
)


class TavilySearcher(BaseProviderSearcher):
    provider = SearchProviderName.TAVILY
    request_class = TavilySearchRequest
    response_mapper = staticmethod(map_tavily_response)

    def __init__(
            self,
            *,
            http_client: httpx.AsyncClient,
            config: SearchProviderConfig,
    ) -> None:
        if not config.api_key:
            raise SearchProviderCredentialError("Tavily API key is required.")
        headers = {
            "Authorization": f"Bearer {config.api_key}",
        }
        super().__init__(http_client=http_client, config=config, headers=headers)
