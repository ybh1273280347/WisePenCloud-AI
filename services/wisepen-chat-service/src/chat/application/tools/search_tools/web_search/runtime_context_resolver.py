from __future__ import annotations

from typing import Protocol

from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import WebSearchSourceKind
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName
from chat.domain.entities.web_search_credential import WebSearchCredentialSource


class WebSearchPlatformCredentialRecord(Protocol):
    """平台搜索凭证实体协议。"""
    source: WebSearchCredentialSource | str


class WebSearchCredentialRuntimeRepository(Protocol):
    """运行期配置层所需的凭证仓储最小接口。"""

    async def get_platform_credential(self, *, user_id: str) -> WebSearchPlatformCredentialRecord | None: ...

    async def get_custom_api_key(self, *, user_id: str, provider: SearchProviderName) -> str: ...


class WebSearchRuntimeContextResolver:
    """将平台或 custom 凭证解析为统一运行时配置。"""

    __slots__ = (
        "_credential_repository",
        "_platform_member_api_key",
        "_platform_member_provider",
    )

    def __init__(
            self,
            *,
            credential_repository: WebSearchCredentialRuntimeRepository,
            platform_member_provider: str | None = None,
            platform_member_api_key: str | None = None,
    ) -> None:
        self._credential_repository = credential_repository
        self._platform_member_provider = _parse_platform_member_provider(platform_member_provider)
        self._platform_member_api_key = (platform_member_api_key or "").strip() or None

    async def resolve(
            self,
            *,
            user_id: str,
            provider: SearchProviderName | None = None,
    ) -> WebSearchRuntimeConfig:
        if provider is not None:
            api_key = await self._credential_repository.get_custom_api_key(
                user_id=user_id,
                provider=provider,
            )
            return WebSearchRuntimeConfig(
                source_kind=WebSearchSourceKind.CUSTOM,
                provider=provider,
                source_id=f"custom:{provider.value}",
                api_key=api_key,
            )

        platform_credential = await self._credential_repository.get_platform_credential(user_id=user_id)
        if (
                platform_credential is not None
                and platform_credential.source == WebSearchCredentialSource.PLATFORM_MEMBER
                and self._platform_member_provider is not None
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
