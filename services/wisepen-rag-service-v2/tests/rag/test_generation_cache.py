from dataclasses import dataclass

import pytest

from rag.core.persistence.mongo import MongoGenerationCacheStore
from rag.domain.entities import GenerationCacheEntity
from rag.domain.generation_cache import GenerationCacheKind


class _Field:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> tuple[str, object]:
        return self.name, other


@dataclass
class _Record:
    resource_id: str
    cache_kind: GenerationCacheKind
    cache_key: str
    payload: str


class _Query:
    def __init__(self, records: list[_Record]) -> None:
        self._records = records
        self.deleted = False

    async def to_list(self) -> list[_Record]:
        return self._records

    async def delete(self) -> None:
        self.deleted = True


class _Collection:
    def __init__(self) -> None:
        self.operations = []

    async def bulk_write(self, operations) -> None:
        self.operations = operations


@pytest.mark.asyncio
async def test_generation_cache_reads_only_matching_resource_kind_and_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        _Record("resource-1", GenerationCacheKind.CONTEXTUAL_TEXT, "key-1", "one"),
        _Record("resource-2", GenerationCacheKind.CONTEXTUAL_TEXT, "key-1", "other-resource"),
        _Record("resource-1", GenerationCacheKind.GRAPH_CANDIDATES, "key-1", "other-kind"),
    ]

    def find(*conditions):
        assert len(conditions) == 3
        assert conditions[0] == ("resource_id", "resource-1")
        assert conditions[1] == ("cache_kind", GenerationCacheKind.CONTEXTUAL_TEXT)
        return _Query([records[0]])

    monkeypatch.setattr(
        GenerationCacheEntity,
        "resource_id",
        _Field("resource_id"),
        raising=False,
    )
    monkeypatch.setattr(
        GenerationCacheEntity,
        "cache_kind",
        _Field("cache_kind"),
        raising=False,
    )
    monkeypatch.setattr(
        GenerationCacheEntity,
        "cache_key",
        _Field("cache_key"),
        raising=False,
    )
    monkeypatch.setattr(GenerationCacheEntity, "find", find)

    result = await MongoGenerationCacheStore().get_many(
        resource_id="resource-1",
        cache_kind=GenerationCacheKind.CONTEXTUAL_TEXT,
        keys=["key-1", "key-1", "missing"],
    )

    assert result == {"key-1": "one"}


@pytest.mark.asyncio
async def test_generation_cache_set_serializes_kind_and_overwrites_by_composite_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _Collection()
    monkeypatch.setattr(
        GenerationCacheEntity,
        "get_pymongo_collection",
        classmethod(lambda cls: collection),
    )

    await MongoGenerationCacheStore().set_many(
        resource_id="resource-1",
        cache_kind=GenerationCacheKind.GRAPH_CANDIDATES,
        values={"key-1": "new-value"},
    )

    operation = collection.operations[0]
    assert operation._filter == {
        "resource_id": "resource-1",
        "cache_kind": "graph_candidates",
        "cache_key": "key-1",
    }
    assert operation._doc["$set"] == {
        "resource_id": "resource-1",
        "cache_kind": "graph_candidates",
        "cache_key": "key-1",
        "payload": "new-value",
    }
    assert operation._upsert is True


@pytest.mark.asyncio
async def test_generation_cache_delete_deduplicates_resource_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = _Query([])
    monkeypatch.setattr(
        GenerationCacheEntity,
        "resource_id",
        _Field("resource_id"),
        raising=False,
    )
    monkeypatch.setattr(GenerationCacheEntity, "find", lambda *conditions: query)

    await MongoGenerationCacheStore().delete_resources(
        ["resource-1", "resource-1", "resource-2"]
    )

    assert query.deleted is True


@pytest.mark.asyncio
async def test_generation_cache_ignores_empty_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def find(*conditions):
        nonlocal called
        called = True
        return _Query([])

    monkeypatch.setattr(GenerationCacheEntity, "find", find)

    store = MongoGenerationCacheStore()
    assert await store.get_many(
        resource_id="resource-1",
        cache_kind=GenerationCacheKind.CONTEXTUAL_TEXT,
        keys=[],
    ) == {}
    await store.delete_resources([])

    assert called is False
