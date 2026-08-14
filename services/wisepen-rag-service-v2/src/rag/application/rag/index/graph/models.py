"""图抽取校验与合并阶段使用的窗口级候选模型。"""

from dataclasses import dataclass, field

from rag.domain.models.graph import (
    KnowledgeEntityType,
    KnowledgeNodeKind,
    KnowledgeRelationType,
)


@dataclass(slots=True)
class KnowledgeEvidence:
    """窗口候选已定位到 SourceRef 的权威证据。"""

    evidence_id: str
    reading_block_id: str
    quote: str
    source_ref_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractedKnowledgeNode:
    local_id: str
    kind: KnowledgeNodeKind
    label: str
    entity_type: KnowledgeEntityType | None = None
    evidence: KnowledgeEvidence | None = None


@dataclass(slots=True)
class ExtractedKnowledgeRelation:
    source_local_id: str
    target_local_id: str
    relation_type: KnowledgeRelationType
    evidence: KnowledgeEvidence
    predicate: str | None = None


@dataclass(slots=True)
class KnowledgeWindowExtraction:
    """一个抽取窗口经过确定性校验后的节点和关系候选。"""

    resource_id: str
    content_revision: str
    nodes: list[ExtractedKnowledgeNode] = field(default_factory=list)
    relations: list[ExtractedKnowledgeRelation] = field(default_factory=list)
