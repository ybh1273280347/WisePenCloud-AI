"""将 GraphRAG 候选图收紧为能够精确回源的领域候选。"""

from hashlib import sha256

from neo4j_graphrag.experimental.components.types import Neo4jGraph, Neo4jNode

from rag.domain.knowledge_graph import (
    ExtractedKnowledgeNode,
    ExtractedKnowledgeRelation,
    KnowledgeAssertion,
    KnowledgeEntityType,
    KnowledgeEvidence,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    KnowledgeWindowExtraction,
)
from rag.utils.chunkers import SourceSpan

from .relations import relation_pattern_allowed
from .windows import KnowledgeExtractionWindow


class KnowledgeCandidateValidator:
    """验证节点、关系、断言和连续原文证据；非法候选直接丢弃。"""

    __slots__ = ("_relations",)

    def __init__(self, relations: frozenset[KnowledgeRelationType]) -> None:
        self._relations = relations

    def validate(
        self,
        graph: Neo4jGraph,
        window: KnowledgeExtractionWindow,
    ) -> KnowledgeWindowExtraction:
        prefix = f"{window.window_id}:"
        nodes = {
            node.id: validated
            for node in graph.nodes
            if node.id.startswith(prefix)
            if (validated := self._validate_node(node, window)) is not None
        }
        relations: dict[tuple[object, ...], ExtractedKnowledgeRelation] = {}
        for candidate in graph.relationships:
            source = nodes.get(candidate.start_node_id)
            target = nodes.get(candidate.end_node_id)
            if source is None or target is None:
                continue
            try:
                relation_type = KnowledgeRelationType(candidate.type)
                assertion = KnowledgeAssertion(
                    _required_text(candidate.properties.get("assertion"))
                )
            except (TypeError, ValueError):
                continue
            if relation_type not in self._relations:
                continue
            if not relation_pattern_allowed(source.kind, relation_type, target.kind):
                continue
            if assertion is not KnowledgeAssertion.AFFIRMED:
                continue

            evidence = _locate_evidence(
                window,
                candidate.properties.get("evidence_quote"),
            )
            if evidence is None:
                continue
            predicate = _optional_text(candidate.properties.get("predicate"))
            if relation_type is KnowledgeRelationType.RELATED_TO and predicate is None:
                continue

            relation = ExtractedKnowledgeRelation(
                source_local_id=source.local_id,
                target_local_id=target.local_id,
                relation_type=relation_type,
                evidence=evidence,
                predicate=predicate,
            )
            relations[
                (
                    source.local_id,
                    target.local_id,
                    relation_type,
                    predicate,
                    evidence.evidence_id,
                )
            ] = relation
        return KnowledgeWindowExtraction(
            resource_id=window.resource_id,
            content_revision=window.content_revision,
            reading_block_id=window.reading_block_id,
            nodes=list(nodes.values()),
            relations=list(relations.values()),
        )

    @staticmethod
    def _validate_node(
        node: Neo4jNode,
        window: KnowledgeExtractionWindow,
    ) -> ExtractedKnowledgeNode | None:
        try:
            kind = KnowledgeNodeKind(node.label)
            label = _required_text(node.properties.get("name"))
        except (TypeError, ValueError):
            return None
        if kind is KnowledgeNodeKind.RESOURCE:
            if node.properties.get("resource_id") != window.resource_id:
                return None
            return ExtractedKnowledgeNode(local_id=node.id, kind=kind, label=label)

        evidence = _locate_evidence(
            window,
            node.properties.get("evidence_quote"),
        )
        if evidence is None:
            return None
        if kind is KnowledgeNodeKind.EXTERNAL_SOURCE:
            return ExtractedKnowledgeNode(
                local_id=node.id,
                kind=kind,
                label=label,
                evidence=evidence,
            )
        try:
            entity_type = KnowledgeEntityType(
                _required_text(node.properties.get("entity_type"))
            )
        except (TypeError, ValueError):
            return None
        return ExtractedKnowledgeNode(
            local_id=node.id,
            kind=kind,
            label=label,
            entity_type=entity_type,
            evidence=evidence,
        )


def _locate_evidence(
    window: KnowledgeExtractionWindow,
    raw_quote: object,
) -> KnowledgeEvidence | None:
    quote = _optional_text(raw_quote)
    if quote is None:
        return None

    search_start = 0
    while True:
        local_start = window.text.find(quote, search_start)
        if local_start < 0:
            return None
        local_end = local_start + len(quote)
        source_span = _map_source_span(window, local_start, local_end)
        if source_span is not None:
            source_ref_ids = list(
                dict.fromkeys(
                    source_ref.ref_id
                    for source_ref in window.source_refs
                    if any(
                        span.start_offset < source_span.end_offset
                        and span.end_offset > source_span.start_offset
                        for span in source_ref.source_spans
                    )
                )
            )
            if source_ref_ids:
                identity = (
                    f"{window.resource_id}\0{window.content_revision}\0"
                    f"{window.reading_block_id}\0{source_span.start_offset}\0"
                    f"{source_span.end_offset}\0{quote}"
                )
                return KnowledgeEvidence(
                    evidence_id=(
                        "knev_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
                    ),
                    reading_block_id=window.reading_block_id,
                    quote=quote,
                    source_span=source_span,
                    source_ref_ids=source_ref_ids,
                )
        # 同一 quote 可能出现多次，继续寻找能够完整落入一条映射的匹配。
        search_start = local_start + 1


def _map_source_span(
    window: KnowledgeExtractionWindow,
    local_start: int,
    local_end: int,
) -> SourceSpan | None:
    for mapping in window.source_mappings:
        if local_start < mapping.window_start or local_end > mapping.window_end:
            continue
        source_start = (
            mapping.source_span.start_offset + local_start - mapping.window_start
        )
        return SourceSpan(source_start, source_start + local_end - local_start)
    return None


def _required_text(value: object) -> str:
    result = _optional_text(value)
    if result is None:
        raise ValueError("required string is missing")
    return result


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None
