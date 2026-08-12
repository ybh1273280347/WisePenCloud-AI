"""Beanie adapter：按资源维护模型生成缓存。"""

from collections.abc import Mapping, Sequence

from beanie.operators import In
from pymongo import UpdateOne

from rag.core.persistence.mongo.mappers.deserializer import to_generation_cache_values
from rag.core.persistence.mongo.mappers.serializer import generation_cache_document
from rag.domain.entities import GenerationCacheEntity
from rag.domain.generation_cache import GenerationCacheKind
from rag.domain.repositories.generation_cache import GenerationCacheStore


class MongoGenerationCacheStore(GenerationCacheStore):
    """隔离资源和 cache kind，提供批量命中、覆盖及资源删除。"""

    async def get_many(
        self,
        *,
        resource_id: str,
        cache_kind: GenerationCacheKind,
        keys: Sequence[str],
    ) -> Mapping[str, str]:
        unique_keys = list(dict.fromkeys(keys))
        if not unique_keys:
            return {}

        records = await GenerationCacheEntity.find(
            GenerationCacheEntity.resource_id == resource_id,
            GenerationCacheEntity.cache_kind == cache_kind,
            In(GenerationCacheEntity.cache_key, unique_keys),
        ).to_list()
        return to_generation_cache_values(records)

    async def set_many(
        self,
        *,
        resource_id: str,
        cache_kind: GenerationCacheKind,
        values: Mapping[str, str],
    ) -> None:
        if not values:
            return

        await GenerationCacheEntity.get_pymongo_collection().bulk_write(
            [
                UpdateOne(
                    {
                        "resource_id": resource_id,
                        "cache_kind": cache_kind.value,
                        "cache_key": cache_key,
                    },
                    {
                        "$set": generation_cache_document(
                            resource_id=resource_id,
                            cache_kind=cache_kind,
                            cache_key=cache_key,
                            payload=payload,
                        )
                    },
                    upsert=True,
                )
                for cache_key, payload in values.items()
            ]
        )

    async def delete_resources(self, resource_ids: Sequence[str]) -> None:
        unique_resource_ids = list(dict.fromkeys(resource_ids))
        if not unique_resource_ids:
            return

        await GenerationCacheEntity.find(
            In(GenerationCacheEntity.resource_id, unique_resource_ids)
        ).delete()
