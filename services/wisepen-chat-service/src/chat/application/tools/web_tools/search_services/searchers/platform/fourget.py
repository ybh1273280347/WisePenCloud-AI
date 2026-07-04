from __future__ import annotations

import httpx

from chat.application.tools.web_tools.search_services.providers.fourget import (
    FourGetSearchRequest,
    map_fourget_response,
)
from chat.application.tools.web_tools.search_services.searchers.base import (
    BaseProviderSearcher,
    SearchProviderConfig,
)


class FourGetSearcher(BaseProviderSearcher):
    provider = None
    request_class = FourGetSearchRequest
    response_mapper = staticmethod(map_fourget_response)

    def __init__(
            self,
            *,
            http_client: httpx.AsyncClient,
            config: SearchProviderConfig,
    ) -> None:
        super().__init__(http_client=http_client, config=config)
