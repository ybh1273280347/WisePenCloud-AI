"""Redis 中候选图子图缓存的序列化、失效和并发填充实现。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from uuid import uuid4

from common.logger import debug, warn
from redis.asyncio import Redis
from redis.exceptions import RedisError

from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import (
    GraphEvidence,
    KnowledgeEntityType,
    KnowledgeMention,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    TraversalDirection,
)
from rag.domain.repositories.neo4j.knowledge_graph_repository import (
    GraphQuerySubgraph,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.repositories.redis.graph_query_subgraph_cache import (
    GraphQuerySubgraphCache,
)
from rag.utils.chunkers import SourceSpan

_CACHE_PREFIX = "wisepen:rag:v2:graph-query-subgraph:"
_EPOCH_KEY = f"{_CACHE_PREFIX}epoch"
_LOCK_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class RedisGraphQuerySubgraphCache(GraphQuerySubgraphCache):
    """缓存 ACL 已过滤但尚未完成证据核验的候选子图。"""

    def __init__(
        self,
        *,
        redis_client: Redis,
        enabled: bool = True,
        ttl_seconds: int = 300,
        max_paths: int = 80,
        max_bytes: int = 1_048_576,
        lock_seconds: int = 3,
    ) -> None:
        if ttl_seconds <= 0 or max_paths <= 0 or max_bytes <= 0 or lock_seconds <= 0:
            raise ValueError("graph query cache limits must be positive")
        self._redis = redis_client
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds
        self._max_paths = max_paths
        self._max_bytes = max_bytes
        self._lock_seconds = lock_seconds
        self._metrics: dict[str, int] = {}

    @property
    def canonical_path_limit(self) -> int:
        return self._max_paths

    @property
    def metrics(self) -> dict[str, int]:
        """返回进程内诊断计数；生产指标采集器可按名称导出它们。"""
        return dict(self._metrics)

    async def get_or_load(
        self,
        *,
        seed_node_ids: Sequence[str],
        permission_scope: PermissionScope,
        relation_types: Sequence[KnowledgeRelationType],
        direction: TraversalDirection,
        max_depth: int,
        path_limit: int,
        mention_limit_per_node: int,
        loader: Callable[[], Awaitable[GraphQuerySubgraph]],
    ) -> GraphQuerySubgraph:
        if not self._enabled or not seed_node_ids or path_limit <= 0:
            self._metric("graph_query_cache_bypass")
            return await loader()

        canonical = self._canonical_query(
            seed_node_ids=seed_node_ids,
            permission_scope=permission_scope,
            relation_types=relation_types,
            direction=direction,
            max_depth=max_depth,
            mention_limit_per_node=mention_limit_per_node,
        )
        # 所有请求都填充同一个候选池上限，小 limit 只在调用方截断。
        canonical["path_limit"] = self._max_paths
        epoch = await self._epoch()
        key = self._cache_key(canonical, epoch)
        cached = await self._read(key, canonical, epoch)
        if cached is not None:
            self._metric("graph_query_cache_hit")
            return cached
        self._metric("graph_query_cache_miss")

        lock_key = f"{key}:lock"
        token = uuid4().hex
        acquired = await self._redis.set(
            lock_key,
            token,
            nx=True,
            ex=self._lock_seconds,
        )
        if not acquired:
            self._metric("graph_query_cache_waited_for_lock")
            # 不阻塞请求等待锁；并发请求各自执行一次查询，但只有持锁者写入。
            return await loader()

        try:
            # 锁等待期间可能已有写入，必须再次读取避免重复构建。
            cached = await self._read(key, canonical, epoch)
            if cached is not None:
                self._metric("graph_query_cache_hit")
                return cached
            loaded = await loader()
            value = replace(
                loaded,
                seed_node_ids=list(canonical["seed_node_ids"]),
                relation_types=[
                    KnowledgeRelationType(value)
                    for value in canonical["relation_types"]
                ],
                direction=direction,
                max_depth=max_depth,
                path_limit=self._max_paths,
                mention_limit_per_node=mention_limit_per_node,
                graph_epoch=epoch,
                cache_schema_version=_CACHE_SCHEMA_VERSION,
            )
            await self._write(key, value, canonical, epoch)
            return value
        finally:
            try:
                await self._redis.eval(_LOCK_RELEASE_SCRIPT, 1, lock_key, token)
            except RedisError:
                debug("graph query cache lock release failed", error="redis eval failed")

    async def bump_epoch(self) -> str:
        value = await self._redis.incr(_EPOCH_KEY)
        epoch = str(value)
        self._metric("graph_query_cache_epoch_bumped")
        return epoch

    async def _epoch(self) -> str:
        value = await self._redis.get(_EPOCH_KEY)
        if value is None:
            created = await self._redis.set(_EPOCH_KEY, "0", nx=True)
            value = "0" if created else await self._redis.get(_EPOCH_KEY)
        if isinstance(value, bytes):
            value = value.decode()
        if not isinstance(value, str) or not value.isdigit():
            raise ValueError("graph query cache epoch is invalid")
        return value

    async def _read(
        self,
        key: str,
        canonical: dict[str, object],
        epoch: str,
    ) -> GraphQuerySubgraph | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode()
            payload = json.loads(raw)
            return _decode(payload, canonical=canonical, epoch=epoch)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            warn(
                "discarding malformed graph query cache payload",
                key=key,
            )
            await self._redis.delete(key)
            return None

    async def _write(
        self,
        key: str,
        value: GraphQuerySubgraph,
        canonical: dict[str, object],
        epoch: str,
    ) -> None:
        encoded = json.dumps(
            _encode(value, canonical=canonical, epoch=epoch),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload_bytes = len(encoded.encode("utf-8"))
        self._metric("graph_query_cache_payload_bytes", payload_bytes=payload_bytes)
        if payload_bytes > self._max_bytes:
            self._metric("graph_query_cache_bypass")
            return
        ttl = min(self._ttl_seconds, 30) if not value.paths else self._ttl_seconds
        await self._redis.set(key, encoded, ex=ttl)

    @staticmethod
    def _cache_key(canonical: dict[str, object], epoch: str) -> str:
        raw = json.dumps(
            {"cache_schema_version": _CACHE_SCHEMA_VERSION, "graph_epoch": epoch, **canonical},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"{_CACHE_PREFIX}{hashlib.sha256(raw).hexdigest()}"

    @staticmethod
    def _canonical_query(
        *,
        seed_node_ids: Sequence[str],
        permission_scope: PermissionScope,
        relation_types: Sequence[KnowledgeRelationType],
        direction: TraversalDirection,
        max_depth: int,
        mention_limit_per_node: int,
    ) -> dict[str, object]:
        roles = sorted(
            [
                group_id,
                role.value if hasattr(role, "value") else role,
            ]
            for group_id, role in permission_scope.group_roles.items()
        )
        return {
            "permission_scope": {
                "user_id": permission_scope.user_id,
                "group_roles": roles,
            },
            "seed_node_ids": sorted(set(seed_node_ids)),
            "relation_types": sorted({item.value for item in relation_types}),
            "direction": direction.value,
            "max_depth": max_depth,
            "mention_limit_per_node": mention_limit_per_node,
        }

    def _metric(self, name: str, **fields: object) -> None:
        if "payload_bytes" in fields:
            self._metrics[name] = self._metrics.get(name, 0) + int(fields["payload_bytes"])
        else:
            self._metrics[name] = self._metrics.get(name, 0) + 1
        debug(name, **fields)


_CACHE_SCHEMA_VERSION = "graph-query-subgraph:v1"


def _encode(
    subgraph: GraphQuerySubgraph,
    *,
    canonical: dict[str, object],
    epoch: str,
) -> dict[str, object]:
    return {
        "cache_schema_version": _CACHE_SCHEMA_VERSION,
        "graph_epoch": epoch,
        "query": canonical,
        "paths": [_encode_path(path) for path in subgraph.paths],
        "mentions": [_encode_mention(mention) for mention in subgraph.mentions],
    }


def _encode_path(path: TraversedPath) -> dict[str, object]:
    return {
        "nodes": [
            {
                "node_id": node.node_id,
                "kind": node.kind.value,
                "label": node.label,
                "entity_type": node.entity_type.value if node.entity_type else None,
                "resource_id": node.resource_id,
            }
            for node in path.nodes
        ],
        "edges": [
            {
                "edge_id": edge.edge_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "relation_type": edge.relation_type.value,
                "predicate": edge.predicate,
                "evidence": [_encode_evidence(item) for item in edge.evidence],
            }
            for edge in path.edges
        ],
    }


def _encode_evidence(item: GraphEvidence) -> dict[str, object]:
    return {
        "evidence_id": item.evidence_id,
        "resource_id": item.resource_id,
        "content_revision": item.content_revision,
        "reading_block_id": item.reading_block_id,
        "quote": item.quote,
        "start_offset": item.source_span.start_offset,
        "end_offset": item.source_span.end_offset,
    }


def _encode_mention(item: KnowledgeMention) -> dict[str, object]:
    return {
        "mention_id": item.mention_id,
        "node_id": item.node_id,
        "evidence": _encode_evidence(item.evidence),
    }


def _decode(
    payload: object,
    *,
    canonical: dict[str, object],
    epoch: str,
) -> GraphQuerySubgraph:
    if not isinstance(payload, dict):
        raise TypeError("cache payload must be an object")
    if payload.get("cache_schema_version") != _CACHE_SCHEMA_VERSION:
        raise ValueError("cache schema version mismatch")
    if payload.get("graph_epoch") != epoch or payload.get("query") != canonical:
        raise ValueError("cache query summary mismatch")
    paths = payload.get("paths")
    mentions = payload.get("mentions")
    if not isinstance(paths, list) or not isinstance(mentions, list):
        raise TypeError("cache collections are invalid")
    return GraphQuerySubgraph(
        paths=[_decode_path(item) for item in paths],
        mentions=[_decode_mention(item) for item in mentions],
        seed_node_ids=list(canonical["seed_node_ids"]),
        relation_types=[KnowledgeRelationType(value) for value in canonical["relation_types"]],
        direction=TraversalDirection(canonical["direction"]),
        max_depth=_positive_int(canonical["max_depth"]),
        path_limit=_positive_int(canonical["path_limit"]),
        mention_limit_per_node=_positive_int(canonical["mention_limit_per_node"]),
        graph_epoch=epoch,
        cache_schema_version=_CACHE_SCHEMA_VERSION,
    )


def _decode_path(item: object) -> TraversedPath:
    if not isinstance(item, dict) or not isinstance(item.get("nodes"), list) or not isinstance(item.get("edges"), list):
        raise TypeError("cache path is invalid")
    nodes = [_decode_node(value) for value in item["nodes"]]
    edges = [_decode_edge(value) for value in item["edges"]]
    if len(nodes) < 2 or len(edges) != len(nodes) - 1:
        raise ValueError("cache path node and edge arrays are misaligned")
    return TraversedPath(nodes=nodes, edges=edges)


def _decode_node(item: object) -> KnowledgeNode:
    if not isinstance(item, dict):
        raise TypeError("cache node is invalid")
    kind = KnowledgeNodeKind(item["kind"])
    entity_type = item.get("entity_type")
    resource_id = item.get("resource_id")
    if kind is KnowledgeNodeKind.ENTITY:
        if entity_type is None:
            raise ValueError("entity cache node is missing entity type")
    elif entity_type is not None:
        raise ValueError("non-entity cache node has entity type")
    if kind is KnowledgeNodeKind.RESOURCE and not isinstance(resource_id, str):
        raise TypeError("resource cache node is missing resource ID")
    if kind is not KnowledgeNodeKind.RESOURCE and resource_id is not None:
        raise ValueError("non-resource cache node has resource ID")
    return KnowledgeNode(
        node_id=_text(item, "node_id"),
        kind=kind,
        label=_text(item, "label"),
        entity_type=KnowledgeEntityType(entity_type) if entity_type is not None else None,
        resource_id=resource_id,
    )


def _decode_edge(item: object) -> TraversedEdge:
    if not isinstance(item, dict) or not isinstance(item.get("evidence"), list):
        raise TypeError("cache edge is invalid")
    return TraversedEdge(
        edge_id=_text(item, "edge_id"),
        source_node_id=_text(item, "source_node_id"),
        target_node_id=_text(item, "target_node_id"),
        relation_type=KnowledgeRelationType(item["relation_type"]),
        predicate=item.get("predicate"),
        evidence=[_decode_evidence(value) for value in item["evidence"]],
    )


def _decode_evidence(item: object) -> GraphEvidence:
    if not isinstance(item, dict):
        raise TypeError("cache evidence is invalid")
    start = _nonnegative_int(item["start_offset"])
    end = _nonnegative_int(item["end_offset"])
    quote = _text(item, "quote")
    if end < start or end - start != len(quote):
        raise ValueError("cache evidence range is invalid")
    return GraphEvidence(
        evidence_id=_text(item, "evidence_id"),
        resource_id=_text(item, "resource_id"),
        content_revision=_text(item, "content_revision"),
        reading_block_id=_text(item, "reading_block_id"),
        source_span=SourceSpan(start, end),
        quote=quote,
    )


def _decode_mention(item: object) -> KnowledgeMention:
    if not isinstance(item, dict) or not isinstance(item.get("evidence"), dict):
        raise TypeError("cache mention is invalid")
    return KnowledgeMention(
        mention_id=_text(item, "mention_id"),
        node_id=_text(item, "node_id"),
        evidence=_decode_evidence(item["evidence"]),
    )


def _text(item: dict[str, object], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise TypeError(f"cache field {field} is invalid")
    return value


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or value <= 0:
        raise TypeError("cache integer field is invalid")
    return value


def _nonnegative_int(value: object) -> int:
    if not isinstance(value, int) or value < 0:
        raise TypeError("cache offset is invalid")
    return value
