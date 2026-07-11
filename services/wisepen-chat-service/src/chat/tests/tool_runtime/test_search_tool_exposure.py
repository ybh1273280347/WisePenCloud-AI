from __future__ import annotations

from types import SimpleNamespace

import pytest

from chat.application.tools.search_tools.exposure import active_search_tool_names
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName


class _FakeCredentialRepository:
    def __init__(self, *, custom: object | None = None, platform: object | None = None) -> None:
        self._custom = custom
        self._platform = platform

    async def get_active_custom_credential(self, *, user_id: str) -> object | None:
        return self._custom

    async def get_platform_credential(self, *, user_id: str) -> object | None:
        return self._platform


@pytest.mark.asyncio
async def test_active_custom_credential_exposes_only_provider_tool() -> None:
    tool_names = await active_search_tool_names(
        user_id="user-1",
        credential_repository=_FakeCredentialRepository(
            custom=SimpleNamespace(provider=SearchProviderName.EXA),
            platform=object(),
        ),
    )

    assert tool_names == {"exa_search"}


@pytest.mark.asyncio
async def test_active_platform_credential_exposes_platform_search() -> None:
    tool_names = await active_search_tool_names(
        user_id="user-1",
        credential_repository=_FakeCredentialRepository(platform=object()),
    )

    assert tool_names == {"platform_search"}


@pytest.mark.asyncio
async def test_no_active_search_credential_exposes_no_search_tools() -> None:
    tool_names = await active_search_tool_names(
        user_id="user-1",
        credential_repository=_FakeCredentialRepository(),
    )

    assert tool_names == set()
