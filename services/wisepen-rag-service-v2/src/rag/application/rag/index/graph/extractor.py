"""编排 GraphRAG 候选抽取、派生产物复用和确定性校验。

``KnowledgeGraphExtractor`` 是图谱抽取的对外入口，职责是：
1. 从 ``GraphBuildSourceReader`` 加载已发布的 ReadingBlock、Section、SourceRef 等素材。
2. 调用 ``build_extraction_windows`` 切分窗口。
3. 复用 ``GenerationArtifactStore`` 中已持久化的 SDK 原始候选图（按 artifact_key 命中）；
   缺失的窗口才调用 LLM 重新抽取。
4. 对每个窗口的候选图执行 ``KnowledgeCandidateValidator.validate``，输出收紧后的
   ``KnowledgeWindowExtraction``。
5. 不负责合并/发布图谱——合并由 ``merge_candidate_graph`` 完成，发布由
   ``KnowledgeGraphWriter`` 完成。

注意：派生产物只保存 SDK 原始候选图（``encode_candidate_graph``），不保存校验后的
``KnowledgeWindowExtraction``。这样在 schema/校验规则变化时仍可重新校验，无需重新调用 LLM。
"""

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

# 派生产物（SDK 原始候选图）的版本号；schema/编码规则变化时递增，使旧 artifact 失效。
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
        # 默认启用所有 profile；调用方可传入子集以限制抽取范围。
        profiles = profiles or frozenset(KnowledgeRelationProfile)
        # 根据 profile 构建 GraphRAG schema，决定允许的关系类型与端点组合。
        self._schema = _build_schema(profiles)
        # 从 schema 中提取实际启用的关系类型，作为 validator 的白名单。
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
        # store_contract 是派生产物缓存的“契约哈希”，涵盖 artifact 版本、SDK 版本、
        # LLM 生成画像、schema 内容；任一变化都会让旧缓存失效，强制重新抽取。
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
        """加载素材、构建窗口、抽取并校验候选，返回每个窗口的 ``KnowledgeWindowExtraction``。

        非 SECTIONED 文档直接返回空列表（无章节上下文，不抽取图谱）。
        """
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
        """对所有窗口执行抽取，命中缓存的窗口复用 SDK 原始候选，缺失的窗口重新抽取。

        关键设计：
        - 缓存命中时，仍会执行 ``KnowledgeCandidateValidator.validate``，因为校验规则
          可能随版本更新而变化，必须保证当前版本规则下产出的结果一致。
        - 缺失的窗口批量调用 ``GraphRagCandidateExtractor.extract``，一次 LLM 调用处理
          多个窗口（SDK 内部并发）；再用 ``slice_candidate_graph`` 切出每个窗口的子图。
        - 新生成的候选图通过 ``encode_candidate_graph`` 写回 artifact store。
        """
        if not windows:
            return []
        # 防御：所有窗口必须属于同一资源同一 revision，否则缓存键会错乱。
        resource_ids = {window.resource_id for window in windows}
        revisions = {window.content_revision for window in windows}
        if len(resource_ids) != 1 or len(revisions) != 1:
            raise ValueError("extraction windows must share one resource revision")

        resource_id = next(iter(resource_ids))
        artifact_keys = [self._artifact_key(window) for window in windows]
        # 批量读取已持久化的 SDK 原始候选图。
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
            # 缺失的窗口一次性送入 SDK 抽取（内部并发）。
            missing_windows = [item[2] for item in missing]
            graph = await self._candidate_extractor.extract(missing_windows, self._schema)
            generated_artifacts: dict[str, str] = {}
            for index, key, window in missing:
                # SDK 返回的是合并图，按 window_id 切出当前窗口子图。
                window_graph = slice_candidate_graph(graph, window.window_id)
                results[index] = self._validator.validate(window_graph, window)
                # 把切出的子图编码为 JSON 持久化，下次重复索引时复用。
                generated_artifacts[key] = encode_candidate_graph(
                    window_graph,
                    window.window_id,
                )
            await self._generation_artifact_store.set_many(
                resource_id=resource_id,
                artifact_kind=GenerationArtifactKind.GRAPH_CANDIDATES,
                artifacts=generated_artifacts,
            )
        # 按窗口原始顺序返回，保证下游合并结果稳定。
        return [results[index] for index in range(len(windows))]

    def _artifact_key(self, window: KnowledgeExtractionWindow) -> str:
        """计算窗口的派生产物缓存键。

        把 store_contract（包含版本/schema/LLM 画像）与窗口渲染文本拼接后哈希，
        保证：
        - 不同窗口文本 → 不同 key（同一窗口重复抽取 → 同一 key，命中缓存）。
        - schema/LLM/版本变化 → 全部 key 失效（强制重新抽取）。
        """
        value = f"{self._store_contract}\0{render_extraction_window(window)}"
        return sha256(value.encode("utf-8")).hexdigest()


def _build_schema(
    profiles: frozenset[KnowledgeRelationProfile],
) -> GraphSchema:
    """根据启用的 profile 构建 GraphRAG SDK 使用的 ``GraphSchema``。

    schema 是发给 LLM 的“抽取契约”，包含：
    - 节点类型（ENTITY / RESOURCE / EXTERNAL_SOURCE）及其属性、必填字段。
    - 关系类型（按 profile 启用）及其属性（evidence_quote / assertion / predicate）。
    - 允许的端点组合 pattern（由 ``relation_pattern_allowed`` 决定）。
    - 存在性约束（必填属性必须出现）。

    schema 严格关闭 ``additional_*``，禁止模型输出 schema 外的字段。
    """
    descriptions = relation_descriptions(profiles)
    # 关系共有的“证据属性”：evidence_quote（原文引用）、assertion（断言）、
    # predicate（RELATED_TO 的具体谓词）。
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
    # 枚举所有合法 (source, relation, target) 三元组，作为 SDK 的 pattern。
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
    # 不同节点类型有不同的属性集合；ENTITY 必须有 entity_type，
    # RESOURCE 必须有 resource_id，EXTERNAL_SOURCE 与 ENTITY 必须有 evidence_quote。
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
        # 存在性约束：必填字段必须出现，否则 SDK 校验失败。
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
