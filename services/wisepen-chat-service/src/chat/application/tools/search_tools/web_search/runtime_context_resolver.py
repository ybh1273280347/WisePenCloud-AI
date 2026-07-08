from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import WebSearchSourceKind
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName
from chat.core.security import SecretCipherError
from chat.domain.entities.web_search_credential import WebSearchCredentialSource


@dataclass(frozen=True, slots=True)
class _CachedCredential:
    api_key: str
    version_key: str


@dataclass(frozen=True, slots=True)
class _PlatformProviderChoice:
    source_kind: WebSearchSourceKind
    provider: SearchProviderName | None
    source_id: str
    api_key: str | None


@runtime_checkable
class WebSearchCredentialRecord(Protocol):
    """搜索凭证实体协议"""
    provider: SearchProviderName | None
    source: WebSearchCredentialSource | str
    api_key_ciphertext: str
    api_key_fingerprint: str
    is_active: bool
    updated_at: datetime | None


class WebSearchCredentialRuntimeRepository(Protocol):
    """运行期配置层所需的凭证仓储最小接口。"""

    async def get_platform_credential(self, *, user_id: str) -> WebSearchCredentialRecord | None: ...

    async def get_active_custom_credential(self, *, user_id: str) -> WebSearchCredentialRecord | None: ...


class WebSearchCredentialCipher(Protocol):
    """运行期密文安全解密内核抽象。"""

    def decrypt(self, ciphertext: str) -> str: ...


class WebSearchRuntimeContextResolver:
    """搜索配置解析器：拦截高频重复解密，统一在内存中维护失效检验缓存。"""

    __slots__ = (
        "_credential_repository",
        "_cipher",
        "_decrypted_credentials",
        "_platform_member_api_key",
        "_platform_member_provider",
    )

    def __init__(
            self,
            *,
            credential_repository: WebSearchCredentialRuntimeRepository,
            cipher: WebSearchCredentialCipher,
            platform_member_provider: str | None = None,
            platform_member_api_key: str | None = None,
    ) -> None:
        self._credential_repository = credential_repository
        self._cipher = cipher
        self._platform_member_provider = _parse_platform_member_provider(platform_member_provider)
        self._platform_member_api_key = (platform_member_api_key or "").strip() or None
        self._decrypted_credentials: dict[
            tuple[str, str, SearchProviderName],
            _CachedCredential,
        ] = {}

    async def resolve(
            self,
            *,
            user_id: str,
            session_id: str,
    ) -> WebSearchRuntimeConfig:
        """多路分流解析：优先引导至自定义密钥，否则平滑退化至平台全局分流。"""
        credential = await self._credential_repository.get_active_custom_credential(user_id=user_id)

        # 1. 平台默认分流路径：无自定义凭证时直接短路返回
        if credential is None or credential.provider is None or not credential.provider.supports_custom_credential:
            platform_choice = await self._resolve_platform_provider(user_id=user_id)
            return WebSearchRuntimeConfig(
                user_id=user_id,
                session_id=session_id,
                search_config_id=platform_choice.source_id,
                source_kind=platform_choice.source_kind,
                provider=platform_choice.provider,
                source_id=platform_choice.source_id,
                api_key=platform_choice.api_key,
            )

        # 2. 自定义凭证路径：基于元数据特征生成唯一版本识别键
        provider = credential.provider
        search_config_id = f"custom:{provider.value}"
        version_key = _credential_version_key(credential)
        cache_key = (user_id, search_config_id, provider)

        cached = self._decrypted_credentials.get(cache_key)

        # 3. 缓存失效判定机制：无记录或最新哈希版本对齐失败，触发安全解密
        if cached is None or cached.version_key != version_key:
            try:
                api_key = self._cipher.decrypt(credential.api_key_ciphertext)
            except SecretCipherError as exc:
                return WebSearchRuntimeConfig(
                    user_id=user_id,
                    session_id=session_id,
                    search_config_id=search_config_id,
                    source_kind=WebSearchSourceKind.CUSTOM,
                    provider=provider,
                    source_id=_custom_source_id(credential),
                    credential_fingerprint=credential.api_key_fingerprint,
                    credential_updated_at=_datetime_to_version(credential.updated_at),
                    is_valid=False,
                    error_message=str(exc),
                )
            cached = _CachedCredential(
                api_key=api_key,
                version_key=version_key,
            )
            self._decrypted_credentials[cache_key] = cached

        return WebSearchRuntimeConfig(
            user_id=user_id,
            session_id=session_id,
            search_config_id=search_config_id,
            source_kind=WebSearchSourceKind.CUSTOM,
            provider=provider,
            source_id=_custom_source_id(credential),
            api_key=cached.api_key,
            credential_fingerprint=credential.api_key_fingerprint,
            credential_updated_at=_datetime_to_version(credential.updated_at),
            is_valid=credential.is_active,
        )

    async def resolve_platform(
            self,
            *,
            user_id: str,
            session_id: str,
    ) -> WebSearchRuntimeConfig:
        """只解析平台源，供 platform_search 使用。"""
        platform_choice = await self._resolve_platform_provider(user_id=user_id)
        return WebSearchRuntimeConfig(
            user_id=user_id,
            session_id=session_id,
            search_config_id=platform_choice.source_id,
            source_kind=platform_choice.source_kind,
            provider=platform_choice.provider,
            source_id=platform_choice.source_id,
            api_key=platform_choice.api_key,
        )

    async def _resolve_platform_provider(
            self,
            *,
            user_id: str,
    ) -> _PlatformProviderChoice:
        """平台源解析：会员源只按配置路由，不与 provider 绑定。"""
        platform_credential = await self._credential_repository.get_platform_credential(user_id=user_id)
        if (
                platform_credential is not None
                and platform_credential.source == WebSearchCredentialSource.PLATFORM_MEMBER
                and self._platform_member_provider is not None
                and self._platform_member_api_key
        ):
            return _PlatformProviderChoice(
                source_kind=WebSearchSourceKind.PLATFORM_MEMBER,
                provider=self._platform_member_provider,
                source_id=f"platform_member:{self._platform_member_provider.value}",
                api_key=self._platform_member_api_key,
            )

        return _PlatformProviderChoice(
            source_kind=WebSearchSourceKind.PLATFORM_DEFAULT,
            provider=None,
            source_id="platform_default",
            api_key=None,
        )


def _credential_version_key(credential: WebSearchCredentialRecord) -> str:
    """复合多项凭证特征，生成内存明文缓存一致性指纹。"""
    source_val = (
        credential.source.value
        if isinstance(credential.source, WebSearchCredentialSource)
        else str(credential.source)
    )
    return "|".join((
        source_val,
        credential.provider.value if credential.provider is not None else "",
        _datetime_to_version(credential.updated_at) or "",
        credential.api_key_fingerprint,
    ))


def _custom_source_id(credential: WebSearchCredentialRecord) -> str:
    """安全混淆自定义源唯一标识码。"""
    fingerprint = credential.api_key_fingerprint[:16] if credential.api_key_fingerprint else "unknown"
    provider_value = credential.provider.value if credential.provider is not None else "unknown"
    return f"custom:{provider_value}:{fingerprint}"


def _parse_platform_member_provider(value: str | None) -> SearchProviderName | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        provider = SearchProviderName(normalized)
    except ValueError:
        return None
    return provider


def _datetime_to_version(value: datetime | None) -> str | None:
    """统一转化时间戳为 ISO 标准的版本化标识字串。"""
    return value.isoformat() if value is not None else None
