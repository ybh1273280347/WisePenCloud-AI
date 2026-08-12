"""知识图谱抽取、合并和发布阶段共享的领域事实。"""

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from rag.utils.chunkers import SourceSpan


class KnowledgeNodeKind(StrEnum):
    ENTITY = "Entity"
    RESOURCE = "Resource"
    EXTERNAL_SOURCE = "ExternalSource"


class KnowledgeEntityType(StrEnum):
    CONCEPT = "concept"
    PERSON = "person"
    ORGANIZATION = "organization"
    PRODUCT = "product"
    TECHNOLOGY = "technology"
    METHOD = "method"
    DATASET = "dataset"
    EVENT = "event"
    PLACE = "place"
    DOCUMENT = "document"
    OTHER = "other"


class KnowledgeRelationProfile(StrEnum):
    CORE = "core"
    LEARNING = "learning"
    SCHOLARLY = "scholarly"


class KnowledgeRelationType(StrEnum):
    MENTIONS = "MENTIONS"
    ABOUT = "ABOUT"
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"
    USES = "USES"
    PRODUCES = "PRODUCES"
    DEPENDS_ON = "DEPENDS_ON"
    DERIVED_FROM = "DERIVED_FROM"
    IMPLEMENTS = "IMPLEMENTS"
    APPLIES_TO = "APPLIES_TO"
    CAUSES = "CAUSES"
    COMPARES_WITH = "COMPARES_WITH"
    CONTRADICTS = "CONTRADICTS"
    EXTENDS = "EXTENDS"
    SUPERSEDES = "SUPERSEDES"
    LOCATED_IN = "LOCATED_IN"
    AUTHORED_BY = "AUTHORED_BY"
    DEFINES = "DEFINES"
    EXPLAINS = "EXPLAINS"
    EXAMPLE_OF = "EXAMPLE_OF"
    REQUIRES = "REQUIRES"
    CITES = "CITES"
    PUBLISHED_IN = "PUBLISHED_IN"
    USES_DATASET = "USES_DATASET"
    USES_METHOD = "USES_METHOD"
    SUPPLEMENTS = "SUPPLEMENTS"
    RETRACTS = "RETRACTS"


class KnowledgeAssertion(StrEnum):
    AFFIRMED = "affirmed"
    NEGATED = "negated"
    CONDITIONAL = "conditional"
    UNCERTAIN = "uncertain"


class GraphStatus(StrEnum):
    """资源图在 Neo4j 中的发布状态。"""

    BUILDING = "building"
    PUBLISHED = "published"
    SKIPPED = "skipped"


@dataclass(slots=True)
class KnowledgeEvidence:
    evidence_id: str
    reading_block_id: str
    quote: str
    source_span: SourceSpan
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
    resource_id: str
    content_revision: str
    reading_block_id: str
    nodes: list[ExtractedKnowledgeNode] = field(default_factory=list)
    relations: list[ExtractedKnowledgeRelation] = field(default_factory=list)


@dataclass(slots=True)
class KnowledgeNode:
    """经过规范化和等价合并的稳定知识节点。"""

    node_id: str
    kind: KnowledgeNodeKind
    label: str
    entity_type: KnowledgeEntityType | None = None
    resource_id: str | None = None


@dataclass(slots=True)
class KnowledgeMention:
    """一个知识节点在当前资源权威原文中的有证据出现。"""

    mention_id: str
    node_id: str
    reading_block_id: str
    source_ref_ids: list[str]
    evidence_quote: str


@dataclass(slots=True)
class KnowledgeRelation:
    """多个窗口中的等价关系及其去重后的证据。"""

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: KnowledgeRelationType
    evidence_quotes: list[str]
    evidence_source_ref_ids: list[str]
    predicate: str | None = None


@dataclass(slots=True)
class KnowledgeGraph:
    """一个内容 revision 合并完成、等待发布的资源知识图谱。"""

    resource_id: str
    content_revision: str
    graph_revision: str
    nodes: list[KnowledgeNode] = field(default_factory=list)
    mentions: list[KnowledgeMention] = field(default_factory=list)
    relations: list[KnowledgeRelation] = field(default_factory=list)


def resource_node_id(resource_id: str) -> str:
    """返回 Resource 节点在图事实和 Neo4j 中共用的稳定 ID。"""
    digest = sha256(f"resource\0{resource_id}".encode()).hexdigest()
    return f"kn_{digest[:32]}"
