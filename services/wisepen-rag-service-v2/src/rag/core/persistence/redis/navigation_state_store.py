"""Redis 导航状态 adapter，所有状态字段共用一个 hash key。"""

import json
from collections.abc import Mapping, Sequence
from uuid import uuid4

from redis.asyncio import Redis

from rag.core.persistence.redis.mappers import (
    deserialize_navigation_state,
    serialize_navigation_state,
    serialize_sections,
)
from rag.domain.navigation import KnownSection, NavigationState
from rag.domain.repositories.navigation_state_store import NavigationStateStore

_KEY_PREFIX = "wisepen:rag:v2:navigation-state:"
_SECTIONS_FIELD = "known_sections"
_NODES_FIELD = "known_nodes"

_ADD_SECTIONS_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
local current = redis.call('HGET', KEYS[1], ARGV[1])
local sections = cjson.decode(current or '{}')
local additions = cjson.decode(ARGV[2])
for section_id, value in pairs(additions) do
    sections[section_id] = value
end
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(sections))
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""

_ADD_NODES_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
local current = redis.call('HGET', KEYS[1], ARGV[1])
local nodes = cjson.decode(current or '[]')
local seen = {}
for _, node_id in ipairs(nodes) do
    seen[node_id] = true
end
local additions = cjson.decode(ARGV[2])
for _, node_id in ipairs(additions) do
    if not seen[node_id] then
        table.insert(nodes, node_id)
        seen[node_id] = true
    end
end
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(nodes))
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""


class NavigationStateNotFoundError(RuntimeError):
    """状态在原子扩展前已过期或不存在。"""


class RedisNavigationStateStore(NavigationStateStore):
    """以单 hash key 保存状态，并统一续期主 key。"""

    def __init__(self, *, redis_client: Redis, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    async def create(
        self,
        *,
        user_id: str,
        session_id: str,
        root_query: str,
        known_sections: Mapping[str, KnownSection],
        known_node_ids: Sequence[str],
    ) -> NavigationState:
        state = NavigationState(
            state_id=f"nav_{uuid4().hex}",
            user_id=user_id,
            session_id=session_id,
            root_query=root_query,
            known_sections=dict(known_sections),
            known_node_ids=list(dict.fromkeys(known_node_ids)),
        )
        key = self._key(state.state_id)
        await self._redis.hset(key, mapping=serialize_navigation_state(state))
        await self._redis.expire(key, self._ttl_seconds)
        return state

    async def get(self, state_id: str) -> NavigationState | None:
        values = await self._redis.hgetall(self._key(state_id))
        if not values:
            return None
        return deserialize_navigation_state(state_id, values)

    async def add_known_sections(
        self,
        *,
        state_id: str,
        sections: Mapping[str, KnownSection],
    ) -> None:
        result = await self._redis.eval(
            _ADD_SECTIONS_SCRIPT,
            1,
            self._key(state_id),
            _SECTIONS_FIELD,
            json.dumps(serialize_sections(sections), ensure_ascii=False),
            self._ttl_seconds,
        )
        if result != 1:
            raise NavigationStateNotFoundError(state_id)

    async def add_known_nodes(
        self,
        *,
        state_id: str,
        node_ids: Sequence[str],
    ) -> None:
        result = await self._redis.eval(
            _ADD_NODES_SCRIPT,
            1,
            self._key(state_id),
            _NODES_FIELD,
            json.dumps(list(dict.fromkeys(node_ids)), ensure_ascii=False),
            self._ttl_seconds,
        )
        if result != 1:
            raise NavigationStateNotFoundError(state_id)

    @staticmethod
    def _key(state_id: str) -> str:
        return f"{_KEY_PREFIX}{state_id}"
