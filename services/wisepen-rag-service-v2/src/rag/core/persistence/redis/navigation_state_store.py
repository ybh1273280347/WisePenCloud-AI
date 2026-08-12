"""Redis 导航状态 adapter，所有状态字段共用一个 hash key。"""

import json
from collections.abc import Mapping, Sequence
from uuid import uuid4

from redis.asyncio import Redis

from rag.domain.navigation import KnownSection, NavigationState
from rag.domain.repositories.navigation_state_store import NavigationStateStore

_KEY_PREFIX = "wisepen:rag:v2:navigation-state:"
_USER_FIELD = "user_id"
_SESSION_FIELD = "session_id"
_ROOT_QUERY_FIELD = "root_query"
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
        await self._redis.hset(key, mapping=self._serialize_state(state))
        await self._redis.expire(key, self._ttl_seconds)
        return state

    async def get(self, state_id: str) -> NavigationState | None:
        values = await self._redis.hgetall(self._key(state_id))
        if not values:
            return None
        return self._deserialize_state(state_id, values)

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
            json.dumps(self._serialize_sections(sections), ensure_ascii=False),
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

    @staticmethod
    def _serialize_sections(
        sections: Mapping[str, KnownSection],
    ) -> dict[str, dict[str, str]]:
        return {
            section_id: {
                "resource_id": section.resource_id,
                "content_revision": section.content_revision,
            }
            for section_id, section in sections.items()
        }

    @classmethod
    def _serialize_state(cls, state: NavigationState) -> dict[str, str]:
        return {
            _USER_FIELD: state.user_id,
            _SESSION_FIELD: state.session_id,
            _ROOT_QUERY_FIELD: state.root_query,
            _SECTIONS_FIELD: json.dumps(
                cls._serialize_sections(state.known_sections),
                ensure_ascii=False,
            ),
            _NODES_FIELD: json.dumps(state.known_node_ids, ensure_ascii=False),
        }

    @staticmethod
    def _deserialize_state(
        state_id: str,
        values: Mapping[object, object],
    ) -> NavigationState:
        sections_value = json.loads(_read_text(values, _SECTIONS_FIELD))
        nodes_value = json.loads(_read_text(values, _NODES_FIELD))
        if not isinstance(sections_value, dict) or not isinstance(nodes_value, list):
            raise TypeError(f"navigation state {state_id} has invalid collection fields")
        known_sections: dict[str, KnownSection] = {}
        for section_id, section in sections_value.items():
            if not isinstance(section_id, str) or not isinstance(section, dict):
                raise TypeError(f"navigation state {state_id} has invalid sections")
            known_sections[section_id] = KnownSection(
                resource_id=_required_nested_text(section, "resource_id"),
                content_revision=_required_nested_text(section, "content_revision"),
            )
        if not all(isinstance(node_id, str) for node_id in nodes_value):
            raise ValueError(f"navigation state {state_id} has invalid node IDs")
        return NavigationState(
            state_id=state_id,
            user_id=_read_text(values, _USER_FIELD),
            session_id=_read_text(values, _SESSION_FIELD),
            root_query=_read_text(values, _ROOT_QUERY_FIELD),
            known_sections=known_sections,
            known_node_ids=list(dict.fromkeys(nodes_value)),
        )


def _read_text(values: Mapping[object, object], field_name: str) -> str:
    value = values.get(field_name)
    if value is None:
        value = values.get(field_name.encode())
    if not isinstance(value, (str, bytes)):
        raise TypeError(f"navigation state field {field_name} is invalid")
    return value.decode() if isinstance(value, bytes) else value


def _required_nested_text(value: Mapping[object, object], field_name: str) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value:
        raise ValueError(f"navigation section field {field_name} is invalid")
    return field_value
