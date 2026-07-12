from datetime import datetime, timezone
from typing import Any

from chat.core.security import SecretCipher
from chat.domain.entities.tool_config import UserToolConfig
from chat.domain.repositories.tool_config_repo import ToolConfigRepository


class MongoToolConfigRepository(ToolConfigRepository):
    def __init__(self, *, secret_cipher: SecretCipher) -> None:
        self._secret_cipher = secret_cipher

    async def get_tool_config(self, user_id: str, tool_name: str) -> UserToolConfig | None:
        entity = await UserToolConfig.find_one(
            UserToolConfig.user_id == user_id,
            UserToolConfig.tool_name == tool_name,
        )
        return self._decrypt_secrets(entity) if entity is not None else None

    async def list_tool_configs(self, user_id: str) -> list[UserToolConfig]:
        entities = await UserToolConfig.find(
            UserToolConfig.user_id == user_id,
        ).sort("-updated_at").to_list()
        return [self._decrypt_secrets(entity) for entity in entities]

    async def upsert_tool_config(
        self,
        *,
        user_id: str,
        tool_name: str,
        enabled: bool,
        config: dict[str, Any],
        secret_config: dict[str, str],
        secret_fingerprints: dict[str, str],
        schema_version: int,
    ) -> UserToolConfig:
        now = datetime.now(timezone.utc)
        await UserToolConfig.get_pymongo_collection().update_one(
            {"user_id": user_id, "tool_name": tool_name},
            {
                "$set": {
                    "enabled": enabled,
                    "config": dict(config),
                    "secret_config": {
                        key: self._secret_cipher.encrypt(value)
                        for key, value in secret_config.items()
                    },
                    "secret_fingerprints": dict(secret_fingerprints),
                    "schema_version": schema_version,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "tool_name": tool_name,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        entity = await self.get_tool_config(user_id, tool_name)
        if entity is None:
            raise RuntimeError("failed to upsert tool config")
        return entity

    async def delete_tool_config(self, user_id: str, tool_name: str) -> None:
        existing = await self.get_tool_config(user_id, tool_name)
        if existing is not None:
            await existing.delete()

    def _decrypt_secrets(self, entity: UserToolConfig) -> UserToolConfig:
        entity.secret_config = {
            key: self._secret_cipher.decrypt(value)
            for key, value in entity.secret_config.items()
        }
        return entity
