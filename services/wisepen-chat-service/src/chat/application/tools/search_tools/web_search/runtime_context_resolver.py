from __future__ import annotations

from typing import Any

from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import WebSearchSourceKind
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName
from chat.application.tools.search_tools.web_search.core.errors import WebSearchCustomApiKeyMissing


class WebSearchRuntimeContextResolver:
    """将平台或 custom 凭证解析为统一运行时配置。"""

    __slots__ = (
        "_platform_member_api_key",
        "_platform_member_provider",
    )

    def __init__(
            self,
            *,
            platform_member_provider: str | None = None,
            platform_member_api_key: str | None = None,
    ) -> None:
        self._platform_member_provider = _parse_platform_member_provider(platform_member_provider)
        self._platform_member_api_key = (platform_member_api_key or "").strip() or None

    async def resolve(
            self,
            *,
            provider: SearchProviderName | None = None,
            config: dict[str, Any] | None = None,
    ) -> WebSearchRuntimeConfig:
        if provider is not None:
            api_key = str((config or {}).get("api_key") or "").strip()
            if not api_key:
                raise WebSearchCustomApiKeyMissing(
                    provider=provider,
                    reason="缺少工具配置中的 API key",
                )
            return WebSearchRuntimeConfig(
                source_kind=WebSearchSourceKind.CUSTOM,
                provider=provider,
                source_id=f"custom:{provider.value}",
                api_key=api_key,
            )

        if (
                self._platform_member_provider is not None
                and self._platform_member_api_key
        ):
            source_id = f"platform_member:{self._platform_member_provider.value}"
            return WebSearchRuntimeConfig(
                source_kind=WebSearchSourceKind.PLATFORM_MEMBER,
                provider=self._platform_member_provider,
                source_id=source_id,
                api_key=self._platform_member_api_key,
            )

        return WebSearchRuntimeConfig(
            source_kind=WebSearchSourceKind.PLATFORM_DEFAULT,
            provider=None,
            source_id="platform_default",
            api_key=None,
        )

def _parse_platform_member_provider(value: str | None) -> SearchProviderName | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        provider = SearchProviderName(normalized)
    except ValueError:
        return None
    return provider
