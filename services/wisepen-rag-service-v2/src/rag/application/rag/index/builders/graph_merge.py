"""把窗口级知识候选规范化并合并为稳定的资源知识图谱。"""

import json
import re
import unicodedata
from hashlib import sha256

from rag.domain.models.graph import (
    ExtractedKnowledgeNode,
    ExtractedKnowledgeRelation,
    KnowledgeEvidence,
    KnowledgeGraph,
    KnowledgeMention,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelation,
    KnowledgeRelationType,
    KnowledgeWindowExtraction,
    resource_node_id,
)

_GRAPH_MERGE_VERSION = "knowledge-graph-merge:v1"


def merge_candidate_graph(
    *,
    resource_id: str,
    content_revision: str,
    extractions: list[KnowledgeWindowExtraction],
) -> KnowledgeGraph:
    """合并同一资源 revision 的已校验窗口候选。"""
    nodes = {
        resource_node_id(resource_id): KnowledgeNode(
            node_id=resource_node_id(resource_id),
            kind=KnowledgeNodeKind.RESOURCE,
            label=resource_id,
            resource_id=resource_id,
        )
    }
    mentions: dict[tuple[str, str], KnowledgeEvidence] = {}
    grouped_relations: dict[
        tuple[str, str, KnowledgeRelationType, str | None],
        list[ExtractedKnowledgeRelation],
    ] = {}

    for extraction in extractions:
        if extraction.resource_id != resource_id:
            raise ValueError("knowledge extraction belongs to another resource")
        if extraction.content_revision != content_revision:
            raise ValueError("knowledge extraction belongs to another revision")

        local_node_ids: dict[str, str] = {}
        for candidate in extraction.nodes:
            node = _canonical_node(candidate, resource_id)
            local_node_ids[candidate.local_id] = node.node_id
            existing = nodes.get(node.node_id)
            if existing is None or _label_sort_key(node.label) < _label_sort_key(
                existing.label
            ):
                nodes[node.node_id] = node

            if candidate.evidence is not None and node.kind is not KnowledgeNodeKind.RESOURCE:
                mentions[(node.node_id, candidate.evidence.evidence_id)] = (
                    candidate.evidence
                )

        for relation in extraction.relations:
            source_node_id = local_node_ids.get(relation.source_local_id)
            target_node_id = local_node_ids.get(relation.target_local_id)
            if source_node_id is None or target_node_id is None:
                continue
            predicate_key = (
                _canonical_key(relation.predicate)
                if relation.relation_type is KnowledgeRelationType.RELATED_TO
                and relation.predicate is not None
                else None
            )
            grouped_relations.setdefault(
                (
                    source_node_id,
                    target_node_id,
                    relation.relation_type,
                    predicate_key,
                ),
                [],
            ).append(relation)

    ordered_nodes = [nodes[node_id] for node_id in sorted(nodes)]
    graph_facts = {
        "version": _GRAPH_MERGE_VERSION,
        "resource_id": resource_id,
        "content_revision": content_revision,
        "nodes": [
            {
                "node_id": node.node_id,
                "kind": node.kind.value,
                "label": node.label,
                "entity_type": (
                    node.entity_type.value if node.entity_type is not None else None
                ),
                "resource_id": node.resource_id,
            }
            for node in ordered_nodes
        ],
        "mentions": [
            {
                "node_id": node_id,
                "evidence_id": evidence_id,
                "reading_block_id": evidence.reading_block_id,
                "quote": evidence.quote,
                "source_ref_ids": sorted(set(evidence.source_ref_ids)),
            }
            for (node_id, evidence_id), evidence in sorted(mentions.items())
        ],
        "relations": [
            _relation_fact(key, relations)
            for key, relations in sorted(
                grouped_relations.items(),
                key=lambda item: (
                    item[0][0],
                    item[0][1],
                    item[0][2].value,
                    item[0][3] or "",
                ),
            )
        ],
    }
    graph_revision = _stable_id(
        "kgr",
        json.dumps(
            graph_facts,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )

    return KnowledgeGraph(
        resource_id=resource_id,
        content_revision=content_revision,
        graph_revision=graph_revision,
        nodes=ordered_nodes,
        mentions=[
            KnowledgeMention(
                mention_id=_stable_id(
                    "knm",
                    graph_revision,
                    node_id,
                    evidence_id,
                ),
                node_id=node_id,
                reading_block_id=evidence.reading_block_id,
                source_ref_ids=sorted(set(evidence.source_ref_ids)),
                evidence_quote=evidence.quote,
            )
            for (node_id, evidence_id), evidence in sorted(mentions.items())
        ],
        relations=[
            _merged_relation(graph_revision, key, relations)
            for key, relations in sorted(
                grouped_relations.items(),
                key=lambda item: (
                    item[0][0],
                    item[0][1],
                    item[0][2].value,
                    item[0][3] or "",
                ),
            )
        ],
    )


def _canonical_node(
    candidate: ExtractedKnowledgeNode,
    resource_id: str,
) -> KnowledgeNode:
    if candidate.kind is KnowledgeNodeKind.RESOURCE:
        return KnowledgeNode(
            node_id=resource_node_id(resource_id),
            kind=KnowledgeNodeKind.RESOURCE,
            label=resource_id,
            resource_id=resource_id,
        )

    label = _normalize_label(candidate.label)
    canonical_key = label.casefold()
    if candidate.kind is KnowledgeNodeKind.EXTERNAL_SOURCE:
        return KnowledgeNode(
            node_id=_stable_id("kn", "external_source", canonical_key),
            kind=candidate.kind,
            label=label,
        )
    if candidate.entity_type is None:
        raise ValueError("entity candidate must provide entity_type")
    return KnowledgeNode(
        node_id=_stable_id(
            "kn",
            "entity",
            candidate.entity_type.value,
            canonical_key,
        ),
        kind=candidate.kind,
        label=label,
        entity_type=candidate.entity_type,
    )


def _relation_fact(
    key: tuple[str, str, KnowledgeRelationType, str | None],
    relations: list[ExtractedKnowledgeRelation],
) -> dict[str, object]:
    source_node_id, target_node_id, relation_type, predicate_key = key
    evidence = {
        relation.evidence.evidence_id: relation.evidence for relation in relations
    }
    return {
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relation_type": relation_type.value,
        "predicate": _relation_predicate(predicate_key, relations),
        "evidence": [
            {
                "evidence_id": evidence_id,
                "quote": item.quote,
                "source_ref_ids": sorted(set(item.source_ref_ids)),
            }
            for evidence_id, item in sorted(evidence.items())
        ],
    }


def _merged_relation(
    graph_revision: str,
    key: tuple[str, str, KnowledgeRelationType, str | None],
    relations: list[ExtractedKnowledgeRelation],
) -> KnowledgeRelation:
    source_node_id, target_node_id, relation_type, predicate_key = key
    evidence = {
        relation.evidence.evidence_id: relation.evidence for relation in relations
    }
    predicate = _relation_predicate(predicate_key, relations)
    return KnowledgeRelation(
        edge_id=_stable_id(
            "kne",
            graph_revision,
            source_node_id,
            target_node_id,
            relation_type.value,
            predicate_key or "",
        ),
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
        predicate=predicate,
        evidence_quotes=sorted({item.quote for item in evidence.values()}),
        evidence_source_ref_ids=sorted(
            {
                source_ref_id
                for item in evidence.values()
                for source_ref_id in item.source_ref_ids
            }
        ),
    )


def _relation_predicate(
    predicate_key: str | None,
    relations: list[ExtractedKnowledgeRelation],
) -> str | None:
    if predicate_key is None:
        return None
    return min(
        _normalize_label(relation.predicate)
        for relation in relations
        if relation.predicate is not None
    )


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", label)).strip()


def _canonical_key(label: str) -> str:
    return _normalize_label(label).casefold()


def _label_sort_key(label: str) -> tuple[str, str]:
    return label.casefold(), label


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"
