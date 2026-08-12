"""知识图谱抽取、合并和发布阶段共享的领域事实。"""

from dataclasses import dataclass, field
from enum import StrEnum

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
