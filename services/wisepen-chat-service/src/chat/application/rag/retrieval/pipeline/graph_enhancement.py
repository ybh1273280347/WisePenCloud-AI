from __future__ import annotations

import json
from hashlib import sha256

from chat.application.rag.cache.graph_enhancement import (
    RagGraphEnhancementCache,
    RagGraphEnhancementCacheKey,
)
from chat.application.rag.graph import (
    RagGraphEnhancementRequest,
    RagGraphEnhancementResult,
    RagGraphRepository,
)


class RagGraphEnhancement:
    """在 direct evidence 通过 hard gate 后执行 Neo4j 后置增强。"""

    __slots__ = (
        "_cache",
        "_graph_version",
        "_ontology_schema_version",
        "_repository",
    )

    def __init__(
        self,
        *,
        repository: RagGraphRepository,
        cache: RagGraphEnhancementCache | None = None,
        graph_version: str = "",
        ontology_schema_version: str = "",
    ) -> None:
        graph_version = graph_version.strip()
        ontology_schema_version = ontology_schema_version.strip()
        if cache is not None and (not graph_version or not ontology_schema_version):
            raise ValueError(
                "graph_version and ontology_schema_version are required when cache is enabled."
            )

        self._repository = repository
        self._cache = cache
        self._graph_version = graph_version
        self._ontology_schema_version = ontology_schema_version

    async def enhance(
        self,
        request: RagGraphEnhancementRequest,
    ) -> RagGraphEnhancementResult:
        if (
            not request.answerability_warning.should_enhance_with_neo4j
            or request.permission_scope is None
            or not request.direct_evidence
        ):
            return RagGraphEnhancementResult()

        cache = self._cache
        if cache is None:
            return await self._repository.expand_for_warnings(request)

        cache_key = _build_cache_key(
            request,
            graph_version=self._graph_version,
            ontology_schema_version=self._ontology_schema_version,
        )
        cached = await cache.get_graph_enhancement(cache_key)
        if cached is not None:
            return cached

        result = await self._repository.expand_for_warnings(request)
        await cache.set_graph_enhancement(cache_key, result)
        return result


def _build_cache_key(
    request: RagGraphEnhancementRequest,
    *,
    graph_version: str,
    ontology_schema_version: str,
) -> RagGraphEnhancementCacheKey:
    permission_scope = request.permission_scope
    if permission_scope is None:
        raise ValueError("permission_scope is required for graph enhancement caching.")

    warning = request.answerability_warning
    return RagGraphEnhancementCacheKey(
        resource_id=request.resource_id,
        direct_evidence_signature=_json_signature([
            {
                "document_version": evidence.document_version,
                "matched_child_ids": list(evidence.matched_child_ids),
            }
            for evidence in request.direct_evidence
        ]),
        warning_signature=_json_signature({
            "warnings": [reason.value for reason in warning.warnings],
            "guidance": warning.guidance,
        }),
        permission_scope_key=_json_signature([
            {
                "group_id": str(group_id),
                "role": getattr(role, "value", str(role)),
            }
            for group_id, role in sorted(
                permission_scope.group_role_map.items(),
                key=lambda item: str(item[0]),
            )
        ]),
        graph_version=graph_version,
        ontology_schema_version=ontology_schema_version,
    )


def _json_signature(payload: object) -> str:
    """生成稳定、紧凑的 JSON SHA-256 签名。"""
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(raw.encode("utf-8")).hexdigest()