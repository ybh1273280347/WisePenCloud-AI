import json

import pytest

from rag.core.persistence.redis import (
    NavigationStateNotFoundError,
    RedisNavigationStateStore,
)
from rag.domain.navigation import KnownSection


class _Redis:
    def __init__(self) -> None:
        self.hashes = {}
        self.expirations = []
        self.eval_calls = []
        self.eval_results = []

    async def hset(self, key, mapping):
        self.hashes[key] = dict(mapping)

    async def expire(self, key, ttl):
        self.expirations.append((key, ttl))

    async def hgetall(self, key):
        return self.hashes.get(key, {})

    async def eval(self, script, numkeys, key, field, value, ttl):
        self.eval_calls.append((script, numkeys, key, field, value, ttl))
        if key not in self.hashes:
            return 0 if field == "known_sections" else None
        current = json.loads(self.hashes[key][field])
        additions = json.loads(value)
        if field == "known_sections":
            current.update(additions)
        else:
            added = []
            for node_id in additions:
                if node_id not in current:
                    current.append(node_id)
                    added.append(node_id)
        self.hashes[key][field] = json.dumps(current, ensure_ascii=False)
        self.expirations.append((key, ttl))
        return 1 if field == "known_sections" else json.dumps(added)


def _store(redis: _Redis) -> RedisNavigationStateStore:
    return RedisNavigationStateStore(redis_client=redis, ttl_seconds=3600)


@pytest.mark.asyncio
async def test_create_and_get_use_one_hash_and_preserve_revision_identity() -> None:
    redis = _Redis()
    state = await _store(redis).create(
        user_id="user-1",
        session_id="session-1",
        root_query="问题",
        known_sections={
            "section-1": KnownSection(
                resource_id="resource-1",
                content_revision="revision-1",
            )
        },
        known_node_ids=["node-1", "node-1"],
    )

    assert len(redis.hashes) == 1
    assert set(redis.hashes[next(iter(redis.hashes))]) == {
        "user_id",
        "session_id",
        "root_query",
        "known_sections",
        "known_nodes",
    }
    assert redis.expirations == [(next(iter(redis.hashes)), 3600)]

    loaded = await _store(redis).get(state.state_id)
    assert loaded is not None
    assert loaded.known_sections["section-1"].content_revision == "revision-1"
    assert loaded.known_node_ids == ["node-1"]


@pytest.mark.asyncio
async def test_add_operations_use_atomic_scripts_and_refresh_same_ttl() -> None:
    redis = _Redis()
    store = _store(redis)
    state = await store.create(
        user_id="user-1",
        session_id="session-1",
        root_query="问题",
        known_sections={},
        known_node_ids=[],
    )

    await store.add_known_sections(
        state_id=state.state_id,
        sections={
            "section-2": KnownSection(
                resource_id="resource-2",
                content_revision="revision-2",
            )
        },
    )
    added = await store.add_known_nodes(
        state_id=state.state_id,
        node_ids=["node-2", "node-2"],
    )

    loaded = await store.get(state.state_id)
    assert loaded is not None
    assert loaded.known_sections["section-2"].resource_id == "resource-2"
    assert loaded.known_node_ids == ["node-2"]
    assert added == ["node-2"]
    assert len(redis.eval_calls) == 2
    assert redis.expirations[-2:] == [(redis.eval_calls[0][2], 3600), (redis.eval_calls[1][2], 3600)]


@pytest.mark.asyncio
async def test_add_operations_raise_when_state_is_missing() -> None:
    store = _store(_Redis())
    with pytest.raises(NavigationStateNotFoundError):
        await store.add_known_nodes(state_id="missing", node_ids=["node"])
    with pytest.raises(NavigationStateNotFoundError):
        await store.add_known_sections(state_id="missing", sections={})
