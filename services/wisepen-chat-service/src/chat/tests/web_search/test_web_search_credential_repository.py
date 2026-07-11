from __future__ import annotations

import sys
import pytest


@pytest.mark.anyio
async def test_get_platform_credential_uses_supported_in_operator(monkeypatch) -> None:
    for module_name in (
            "beanie.operators",
            "beanie",
            "chat.core.persistence.mongo.web_search_credential_repository",
            "chat.domain.entities.web_search_credential",
            "chat.domain.entities",
            "chat.domain.error_codes",
            "common.logger",
            "common.core.domain",
            "common.core.exceptions",
            "common.core",
            "common",
    ):
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    from chat.core.persistence.mongo.web_search_credential_repository import (
        MongoWebSearchCredentialRepository,
    )
    from chat.domain.entities.web_search_credential import WebSearchCredential

    captured_conditions = []

    async def _find_one(*conditions):
        captured_conditions.extend(conditions)
        return None

    monkeypatch.setattr(WebSearchCredential, "find_one", staticmethod(_find_one))
    monkeypatch.setattr(WebSearchCredential, "user_id", _FakeField("user_id"), raising=False)
    monkeypatch.setattr(WebSearchCredential, "source", _FakeField("source"), raising=False)
    monkeypatch.setattr(WebSearchCredential, "is_active", _FakeField("is_active"), raising=False)
    repository = MongoWebSearchCredentialRepository(secret_cipher=object())

    credential = await repository.get_platform_credential(user_id="user-1")

    assert credential is None
    assert len(captured_conditions) == 3


class _FakeField:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> tuple[str, str, object]:  # type: ignore[override]
        return ("eq", self.name, other)
