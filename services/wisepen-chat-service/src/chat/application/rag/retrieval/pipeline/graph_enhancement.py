from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING

from chat.application.rag.cache.graph_enhancement import (
    RagGraphEnhancementCache,
    RagGraphEnhancementCacheKey,
)
from chat.application.rag.graph import (
    RagGraphEnhancementRequest,
    RagGraphEnhancementResult,
    RagGraphRepository,
)

if TYPE_CHECKING:
    from chat.application.rag.context_builder.models import RagDirectEvidence


class RagGraphEnhancement:
    """Soft Gate warning 后的 Neo4j 后置增强步骤。

    Graph 只在 direct evidence 已经通过 hard gate 后补充相关证据；缓存 key 绑定证据签名、
    warning 和 ACL scope，避免跨权限复用。
    """

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
        self._repository = repository
        self._cache = cache
        self._graph_version = graph_version
        self._ontology_schema_version = ontology_schema_version

    async def enhance(self, request: RagGraphEnhancementRequest) -> RagGraphEnhancementResult:
        if not request.answerability_warning.should_enhance_with_neo4j:
            return RagGraphEnhancementResult()
        if request.permission_scope is None:
            return RagGraphEnhancementResult()
        if not request.direct_evidence:
            return RagGraphEnhancementResult()

        cache_key = _build_cache_key(
            request,
            graph_version=self._graph_version,
            ontology_schema_version=self._ontology_schema_version,
        )
        if self._cache is not None:
            cached = await self._cache.get_graph_enhancement(cache_key)
            if cached is not None:
                return cached

        result = await self._repository.expand_for_warnings(request)
        if self._cache is not None:
            await self._cache.set_graph_enhancement(cache_key, result)
        return result


def _build_cache_key(
        request: RagGraphEnhancementRequest,
        *,
        graph_version: str,
        ontology_schema_version: str,
) -> RagGraphEnhancementCacheKey:
    return RagGraphEnhancementCacheKey(
        resource_id=request.resource_id,
        direct_evidence_signature=_direct_evidence_signature(request.direct_evidence),
        warning_signature=_warning_signature(request),
        permission_scope_key=_permission_scope_cache_key(request.permission_scope.group_role_map),
        graph_version=graph_version or "latest",
        ontology_schema_version=ontology_schema_version or "default",
    )


def _direct_evidence_signature(evidence_items: tuple[RagDirectEvidence, ...]) -> str:
    payload = [
        {
            "document_version": evidence.document_version,
            "matched_child_ids": list(evidence.matched_child_ids),
        }
        for evidence in evidence_items
    ]
    return _hash_payload(payload)


def _warning_signature(request: RagGraphEnhancementRequest) -> str:
    return _hash_payload(
        {
            "warnings": [
                reason.value
                for reason in request.answerability_warning.warnings
            ],
            "guidance": request.answerability_warning.guidance,
        }
    )


def _permission_scope_cache_key(group_role_map: dict[str, str]) -> str:
    return "|".join(
        f"{group_id}:{role}"
        for group_id, role in sorted(group_role_map.items())
    )


def _hash_payload(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha256(raw.encode("utf-8")).hexdigest()
