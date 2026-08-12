"""编排 GraphRAG 候选抽取、派生产物复用和确定性校验。"""

from hashlib import sha256

from neo4j_graphrag import __version__ as graph_rag_version
from neo4j_graphrag.experimental.components.schema import (
    ConstraintType,
    GraphConstraintType,
    GraphSchema,
    NodeType,
    Pattern,
    PropertyType,
    RelationshipType,
)

from rag.domain.models.structure import StructureMode
from rag.domain.models.generation import GenerationArtifactKind
from rag.domain.models.graph import (
    KnowledgeEntityType,
    KnowledgeNodeKind,
    KnowledgeRelationProfile,
    KnowledgeRelationType,
    KnowledgeWindowExtraction,
)
from rag.domain.repositories.mongo.generation_artifact_store import GenerationArtifactStore
from rag.domain.repositories.mongo.readers.graph_build_source import GraphBuildSourceReader

from .candidate_codec import (
    decode_candidate_graph,
    encode_candidate_graph,
    slice_candidate_graph,
)
from .candidate_validator import KnowledgeCandidateValidator
from .llm import GraphRagCandidateExtractor, QueryClientGraphRagLLM
from .relations import relation_descriptions, relation_pattern_allowed
from .windows import (
    KnowledgeExtractionWindow,
    build_extraction_windows,
    render_extraction_window,
)

_ARTIFACT_VERSION = "graph-candidates:v1"


class KnowledgeGraphExtractor:
    """抽取并校验窗口级知识候选，不负责合并或发布图谱。"""

    def __init__(
            self, *,
            llm: QueryClientGraphRagLLM,
            generation_artifact_store: GenerationArtifactStore,
            source_reader: GraphBuildSourceReader,
            max_concurrency: int = 5,
            profiles: frozenset[KnowledgeRelationProfile] | None = None) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        profiles = profiles or frozenset(KnowledgeRelationProfile)
        self._schema = _build_schema(profiles)
        active_relations = frozenset(
            KnowledgeRelationType(item.label)
            for item in self._schema.relationship_types
        )
        self._validator = KnowledgeCandidateValidator(active_relations)
        self._candidate_extractor = GraphRagCandidateExtractor(
            llm=llm,
            max_concurrency=max_concurrency,
        )
        self._generation_artifact_store = generation_artifact_store
        self._source_reader = source_reader
        self._store_contract = sha256(
            (
                f"{_ARTIFACT_VERSION}\0{graph_rag_version}\0{llm.artifact_profile}\0"
                f"{self._schema.model_dump_json(exclude_none=True)}"
            ).encode()
        ).hexdigest()

    async def extract(
        self,
        *,
        resource_id: str,
        content_revision: str,
    ) -> list[KnowledgeWindowExtraction]:
        source = await self._source_reader.get_graph_build_source(
            resource_id,
            content_revision,
        )
        if source.structure_mode is not StructureMode.SECTIONED:
            return []
        return await self._extract_windows(build_extraction_windows(source))

    async def _extract_windows(
        self,
        windows: list[KnowledgeExtractionWindow],
    ) -> list[KnowledgeWindowExtraction]:
        if not windows:
            return []
        resource_ids = {window.resource_id for window in windows}
        revisions = {window.content_revision for window in windows}
        if len(resource_ids) != 1 or len(revisions) != 1:
            raise ValueError("extraction windows must share one resource revision")

        resource_id = next(iter(resource_ids))
        artifact_keys = [self._artifact_key(window) for window in windows]
        stored_artifacts = await self._generation_artifact_store.get_many(
            resource_id=resource_id,
            artifact_kind=GenerationArtifactKind.GRAPH_CANDIDATES,
            artifact_keys=artifact_keys,
        )
        results: dict[int, KnowledgeWindowExtraction] = {}
        missing: list[tuple[int, str, KnowledgeExtractionWindow]] = []
        for index, (key, window) in enumerate(zip(artifact_keys, windows, strict=True)):
            graph = (
                decode_candidate_graph(stored_artifacts[key], window.window_id)
                if key in stored_artifacts
                else None
            )
            if graph is None:
                missing.append((index, key, window))
                continue
            # 派生产物只保存 SDK 原始候选；命中后仍执行当前版本的确定性校验。
            results[index] = self._validator.validate(graph, window)

        if missing:
            missing_windows = [item[2] for item in missing]
            graph = await self._candidate_extractor.extract(missing_windows, self._schema)
            generated_artifacts: dict[str, str] = {}
            for index, key, window in missing:
                window_graph = slice_candidate_graph(graph, window.window_id)
                results[index] = self._validator.validate(window_graph, window)
                generated_artifacts[key] = encode_candidate_graph(
                    window_graph,
                    window.window_id,
                )
            await self._generation_artifact_store.set_many(
                resource_id=resource_id,
                artifact_kind=GenerationArtifactKind.GRAPH_CANDIDATES,
                artifacts=generated_artifacts,
            )
        return [results[index] for index in range(len(windows))]

    def _artifact_key(self, window: KnowledgeExtractionWindow) -> str:
        value = f"{self._store_contract}\0{render_extraction_window(window)}"
        return sha256(value.encode("utf-8")).hexdigest()


def _build_schema(
    profiles: frozenset[KnowledgeRelationProfile],
) -> GraphSchema:
    descriptions = relation_descriptions(profiles)
    evidence_properties = [
        PropertyType(
            name="evidence_quote",
            type="STRING",
            description="current_reading_block 中支持关系的连续原文",
        ),
        PropertyType(
            name="assertion",
            type="STRING",
            description="affirmed、negated、conditional 或 uncertain",
        ),
        PropertyType(
            name="predicate",
            type="STRING",
            description="RELATED_TO 的具体谓词",
        ),
    ]
    relationship_types = tuple(
        RelationshipType(
            label=relation.value,
            description=description,
            properties=evidence_properties,
            additional_properties=False,
        )
        for relation, description in descriptions.items()
    )
    patterns = tuple(
        Pattern(
            source=source.value,
            relationship=relation.value,
            target=target.value,
        )
        for source in KnowledgeNodeKind
        for relation in descriptions
        for target in KnowledgeNodeKind
        if relation_pattern_allowed(source, relation, target)
    )
    node_properties = {
        KnowledgeNodeKind.ENTITY: [
            PropertyType(name="name", type="STRING"),
            PropertyType(
                name="entity_type",
                type="STRING",
                description=", ".join(item.value for item in KnowledgeEntityType),
            ),
            PropertyType(name="evidence_quote", type="STRING"),
        ],
        KnowledgeNodeKind.RESOURCE: [
            PropertyType(name="name", type="STRING"),
            PropertyType(name="resource_id", type="STRING"),
        ],
        KnowledgeNodeKind.EXTERNAL_SOURCE: [
            PropertyType(name="name", type="STRING"),
            PropertyType(name="evidence_quote", type="STRING"),
        ],
    }
    required_node_properties = {
        KnowledgeNodeKind.ENTITY: ("name", "entity_type", "evidence_quote"),
        KnowledgeNodeKind.RESOURCE: ("name", "resource_id"),
        KnowledgeNodeKind.EXTERNAL_SOURCE: ("name", "evidence_quote"),
    }
    return GraphSchema(
        node_types=tuple(
            NodeType(
                label=kind.value,
                description=kind.value,
                properties=properties,
                additional_properties=False,
            )
            for kind, properties in node_properties.items()
        ),
        relationship_types=relationship_types,
        patterns=patterns,
        constraints=(
            *(
                ConstraintType(
                    type=GraphConstraintType.EXISTENCE,
                    property_names=(property_name,),
                    node_type=kind.value,
                )
                for kind, property_names in required_node_properties.items()
                for property_name in property_names
            ),
            *(
                ConstraintType(
                    type=GraphConstraintType.EXISTENCE,
                    property_names=(property_name,),
                    relationship_type=relation.value,
                )
                for relation in descriptions
                for property_name in ("evidence_quote", "assertion")
            ),
        ),
        additional_node_types=False,
        additional_relationship_types=False,
        additional_patterns=False,
    )
