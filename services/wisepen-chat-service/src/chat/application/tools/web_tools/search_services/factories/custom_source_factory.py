from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.web_tools.search_services.core.errors import (
    WebSearchCustomApiKeyInvalid,
    WebSearchCustomApiKeyMissing,
)
from chat.application.tools.web_tools.search_services.factories.integration_searcher_factory import (
    IntegrationSearcherFactory,
)
from chat.application.tools.web_tools.search_services.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.web_tools.search_services.core.sources import CustomSearchSource, WebSearchSourceKind


@dataclass(frozen=True, slots=True)
class WebSearchCustomSourceFactory:
    """按已固化到 context 的运行期配置构造 custom 搜索源。"""

    integration_searcher_factory: IntegrationSearcherFactory

    def build(self, config: WebSearchRuntimeConfig) -> CustomSearchSource:
        if config.source_kind != WebSearchSourceKind.CUSTOM:
            raise WebSearchCustomApiKeyInvalid(
                provider=config.provider,
                reason="运行时配置不是 custom 搜索源",
            )
        if not config.api_key:
            raise WebSearchCustomApiKeyMissing(
                provider=config.provider,
                reason="不存在 api key",
            )
        provider = config.provider
        if provider is None or not provider.supports_custom_credential:
            raise WebSearchCustomApiKeyInvalid(
                provider=provider,
                reason="该 provider 不支持 custom 搜索",
            )
        searcher = self.integration_searcher_factory.build(
            provider=provider,
            api_key=config.api_key,
            source_id=config.source_id,
        )
        return CustomSearchSource(
            provider=provider,
            source_id=config.source_id,
            searcher=searcher,
            api_key=config.api_key,
        )
