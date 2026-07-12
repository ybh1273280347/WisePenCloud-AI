from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from chat.core.persistence.mongo.tool_config_repository import MongoToolConfigRepository
from chat.core.security import SecretCipher
from chat.domain.entities.tool_config import UserToolConfig


class _FakeCollection:
    def __init__(self) -> None:
        self.update: dict[str, object] | None = None

    async def update_one(
            self,
            selector: dict[str, object],
            update: dict[str, object],
            *,
            upsert: bool,
    ) -> None:
        self.update = update


@pytest.mark.asyncio
async def test_tool_config_repository_encrypts_secret_values(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_cipher = SecretCipher(encryption_key=Fernet.generate_key().decode("utf-8"))
    repository = MongoToolConfigRepository(secret_cipher=secret_cipher)
    collection = _FakeCollection()
    entity = SimpleNamespace()

    monkeypatch.setattr(
        UserToolConfig,
        "get_pymongo_collection",
        lambda: collection,
    )

    async def get_tool_config(user_id: str, tool_name: str) -> object:
        return entity

    monkeypatch.setattr(repository, "get_tool_config", get_tool_config)

    result = await repository.upsert_tool_config(
        user_id="user-1",
        tool_name="exa_search",
        enabled=True,
        config={},
        secret_config={"api_key": "user-secret"},
        secret_fingerprints={"api_key": "fingerprint"},
        schema_version=1,
    )

    assert result is entity
    assert collection.update is not None
    encrypted = collection.update["$set"]["secret_config"]["api_key"]
    assert encrypted != "user-secret"
    assert secret_cipher.decrypt(encrypted) == "user-secret"


def test_tool_config_repository_decrypts_secret_values() -> None:
    secret_cipher = SecretCipher(encryption_key=Fernet.generate_key().decode("utf-8"))
    repository = MongoToolConfigRepository(secret_cipher=secret_cipher)
    entity = SimpleNamespace(
        secret_config={"api_key": secret_cipher.encrypt("user-secret")},
    )

    result = repository._decrypt_secrets(entity)

    assert result.secret_config == {"api_key": "user-secret"}
