from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

from chat.core.persistence._utils.payload_readers import (
    read_optional_trimmed_str,
    read_trimmed_str_sequence,
)
from chat.application.rag.acl import RagResourceAclProjection
from chat.application.rag.graph import (
    RagConceptPath,
    RagGraphEnhancementRequest,
    RagGraphEnhancementResult,
    RagGraphEvidence,
    RagOntologyHint,
)
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder


class RagNeo4jRepository:
    """RAG Neo4j evidence graph 投影与后置增强查询。"""

    __slots__ = ("_driver", "_permission_filter_builder")

    def __init__(
            self,
            *,
            driver: AsyncDriver | None,
            permission_filter_builder: RagPermissionFilterBuilder,
    ) -> None:
        self._driver = driver
        self._permission_filter_builder = permission_filter_builder

    async def delete_document_projection(
            self,
            *,
            resource_id: str,
            document_version: str,
    ) -> None:
        if self._driver is None:
            return

        await self._driver.execute_query(
            """
            MATCH (chunk:RagChunk {resource_id: $resource_id, document_version: $document_version})
            DETACH DELETE chunk
            """,
            resource_id=resource_id,
            document_version=document_version,
        )
        await self._driver.execute_query(
            """
            MATCH (document:RagDocument {resource_id: $resource_id, document_version: $document_version})
            DETACH DELETE document
            """,
            resource_id=resource_id,
            document_version=document_version,
        )
        await self._driver.execute_query(
            """
            MATCH (entity:__Entity__)
            WHERE NOT (entity)-[:FROM_CHUNK]->(:RagChunk)
            DETACH DELETE entity
            """,
        )

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        if self._driver is None:
            return

        await self._driver.execute_query(
            """
            MATCH (chunk:RagChunk {resource_id: $resource_id})
            SET chunk.owner_id = $owner_id,
                chunk.readable_users = $readable_users,
                chunk.computed_group_acls = $computed_group_acls
            """,
            resource_id=projection.resource_id,
            **_acl_params(projection),
        )

    async def expand_for_warnings(
            self,
            request: RagGraphEnhancementRequest,
    ) -> RagGraphEnhancementResult:
        if self._driver is None or request.permission_scope is None:
            return RagGraphEnhancementResult()

        seed_chunk_ids = _seed_chunk_ids(request)
        if not seed_chunk_ids:
            return RagGraphEnhancementResult()

        predicate, acl_params = self._permission_filter_builder.build_neo4j_predicate(
            request.permission_scope,
            node_alias="candidate",
        )
        # 只从已命中的 direct evidence 种子向外扩展，并在 candidate 上再次应用 ACL。
        records, _, _ = await self._driver.execute_query(
            f"""
            MATCH (seed:RagChunk)
            WHERE seed.chunk_id IN $seed_chunk_ids
            MATCH (seed)<-[:FROM_CHUNK]-(entity:__Entity__)-[:FROM_CHUNK]->(candidate:RagChunk)
            WHERE candidate.chunk_id <> seed.chunk_id
              AND candidate.resource_id = $resource_id
              AND {predicate}
            WITH candidate,
                 collect(DISTINCT seed.chunk_id) AS support_seed_ids,
                 collect(DISTINCT coalesce(entity.name, entity.id, elementId(entity))) AS related_concepts
            RETURN candidate.chunk_id AS chunk_id,
                   candidate.document_version AS document_version,
                   candidate.evidence_text AS evidence_text,
                   candidate.page_label AS page_label,
                   candidate.section_path AS section_path,
                   candidate.anchor_labels AS anchor_labels,
                   support_seed_ids,
                   related_concepts,
                   size(support_seed_ids) AS score
            ORDER BY score DESC, chunk_id ASC
            LIMIT $limit
            """,
            seed_chunk_ids=list(seed_chunk_ids),
            resource_id=request.resource_id,
            limit=max(0, request.limit),
            **acl_params,
        )
        graph_evidence = tuple(_to_graph_evidence(record) for record in records)
        hints = _warning_hints(request) if graph_evidence else ()
        paths = tuple(
            RagConceptPath(
                source_concept="direct_evidence",
                target_concept=item.chunk_id,
                path=item.path,
                support_chunk_ids=tuple(item.path),
            )
            for item in graph_evidence
        )
        return RagGraphEnhancementResult(
            graph_evidence=graph_evidence,
            ontology_hints=hints,
            concept_paths=paths,
        )


def _acl_params(projection: RagResourceAclProjection | None) -> dict[str, Any]:
    if projection is None:
        return {
            "owner_id": "",
            "readable_users": [],
            "computed_group_acls": [],
        }
    return {
        "owner_id": projection.owner_id,
        "readable_users": list(projection.readable_users),
        "computed_group_acls": [
            {
                "group_id": item.group_id,
                "is_readable": item.is_readable,
                "readable_users": list(item.readable_users),
                "excluded_read_users": list(item.excluded_read_users),
            }
            for item in projection.computed_group_acls
        ],
    }


def _seed_chunk_ids(request: RagGraphEnhancementRequest) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for evidence in request.direct_evidence:
        for child_id in evidence.matched_child_ids:
            seen.setdefault(child_id, None)
    return tuple(seen)


def _to_graph_evidence(record: Any) -> RagGraphEvidence:
    chunk_id = str(record["chunk_id"])
    page_label = read_optional_trimmed_str(record.get("page_label"))
    section_path = read_trimmed_str_sequence(record.get("section_path"))
    anchor_labels = read_trimmed_str_sequence(record.get("anchor_labels"))
    path = read_trimmed_str_sequence(record.get("support_seed_ids")) + (chunk_id,)
    return RagGraphEvidence(
        chunk_id=chunk_id,
        document_version=str(record["document_version"]),
        evidence_text=str(record.get("evidence_text") or ""),
        page_label=page_label,
        section_path=section_path,
        anchor_labels=anchor_labels,
        path=path,
        related_concepts=read_trimmed_str_sequence(record.get("related_concepts")),
    )


def _warning_hints(request: RagGraphEnhancementRequest) -> tuple[RagOntologyHint, ...]:
    return tuple(
        RagOntologyHint(
            concept=reason.value,
            path_preview=("direct_evidence", "sibling_chunk_evidence"),
        )
        for reason in request.answerability_warning.warnings
    )
