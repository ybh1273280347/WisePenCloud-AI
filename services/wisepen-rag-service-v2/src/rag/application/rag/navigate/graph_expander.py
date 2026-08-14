"""从 navigation state 的已知节点扩展有 ReadingBlock 证据的知识路径。"""

import json
from dataclasses import dataclass, field

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import (
    KnowledgeEntityType,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    TraversalDirection,
)
from rag.domain.repositories.mongo.published_resource_reader import (
    PublishedGraphEvidence,
)
from rag.domain.repositories.neo4j.knowledge_graph_repository import (
    KnowledgeGraphRepository,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.repositories.redis.navigation_state_store import (
    NavigationStateMissingError,
    NavigationStateStore,
)
from rag.utils.ranking import (
    RankCandidate,
    RankingPipeline,
    RankQuery,
    RankRequest,
)

from .graph_evidence_verifier import GraphEvidenceVerifier
from .views import (
    GraphEvidenceSectionView,
    build_graph_evidence_section_views,
)


class UnknownSeedNodeError(RuntimeError):
    """请求的 seed 尚未被当前 navigation state 发现。"""


class GraphAccessRevokedError(RuntimeError):
    """图谱展开期间证据所属资源失去可读权限。"""


class NavigationStateNotFoundError(RuntimeError):
    """导航状态不存在，或不属于当前用户与会话。"""


@dataclass(slots=True)
class GraphExpandRequest:
    state_id: str
    session_id: str
    permission_scope: PermissionScope
    seed_node_ids: list[str]
    query: str
    relation_types: list[KnowledgeRelationType] = field(default_factory=list)
    direction: TraversalDirection = TraversalDirection.BOTH
    max_depth: int = 1
    max_results: int = 10


@dataclass(slots=True)
class GraphEvidenceRangeView:
    """相对于证据 ReadingBlock 文本的 Python 字符半开区间。"""

    start_offset: int
    end_offset: int


@dataclass(slots=True)
class GraphEvidenceRefView:
    """图事实或节点提及到完整 ReadingBlock 的公开交叉引用。"""

    evidence_id: str
    resource_id: str
    reading_block_id: str
    quote: str
    range: GraphEvidenceRangeView


@dataclass(slots=True)
class DiscoveredKnowledgeNodeView:
    """本次原子写入 state 的新节点及其提及证据。"""

    node_id: str
    label: str
    kind: KnowledgeNodeKind
    entity_type: KnowledgeEntityType | None = None
    evidence: list[GraphEvidenceRefView] = field(default_factory=list)


@dataclass(slots=True)
class GraphPathStepView:
    """按关系语义方向表达的单步路径及其关系证据。"""

    relation: str
    evidence: list[GraphEvidenceRefView] = field(default_factory=list)


@dataclass(slots=True)
class GraphPathView:
    """模型可直接阅读的有向路径，node IDs 只保留作后续导航锚点。"""

    text: str
    node_ids: list[str] = field(default_factory=list)
    steps: list[GraphPathStepView] = field(default_factory=list)


@dataclass(slots=True)
class GraphExpandResult:
    state_id: str
    discovered_nodes: list[DiscoveredKnowledgeNodeView] = field(default_factory=list)
    paths: list[GraphPathView] = field(default_factory=list)
    evidence_sections: list[GraphEvidenceSectionView] = field(default_factory=list)


@dataclass(slots=True)
class _EligiblePath:
    """关系与新节点证据都已核验、等待原子 state 竞争的路径。"""

    path: TraversedPath
    node_evidence: dict[str, list[PublishedGraphEvidence]] = field(
        default_factory=dict
    )


class KnowledgeGraphExpander:
    """编排知识关系遍历、证据核验、路径排序和状态原子扩展。"""

    def __init__(
        self,
        *,
        knowledge_graph: KnowledgeGraphRepository,
        ranking_pipeline: RankingPipeline,
        evidence_verifier: GraphEvidenceVerifier,
        authorizer: PermissionAuthorizer,
        state_store: NavigationStateStore,
    ) -> None:
        self._knowledge_graph = knowledge_graph
        self._ranking_pipeline = ranking_pipeline
        self._evidence_verifier = evidence_verifier
        self._authorizer = authorizer
        self._state_store = state_store

    async def expand(self, request: GraphExpandRequest) -> GraphExpandResult:
        state = await self._state_store.get(request.state_id)
        if (
            state is None
            or state.user_id != request.permission_scope.user_id
            or state.session_id != request.session_id
        ):
            raise NavigationStateNotFoundError(request.state_id)

        known_node_ids = set(state.known_node_ids)
        unknown_seed_ids = [
            node_id
            for node_id in request.seed_node_ids
            if node_id not in known_node_ids
        ]
        if unknown_seed_ids:
            raise UnknownSeedNodeError(unknown_seed_ids[0])

        paths = await self._knowledge_graph.find_paths(
            seed_node_ids=request.seed_node_ids,
            permission_scope=request.permission_scope,
            relation_types=request.relation_types,
            direction=request.direction,
            max_depth=request.max_depth,
            limit=min(request.max_results * 4, 80),
        )
        paths = await self._filter_readable_paths(paths, request.permission_scope)
        paths = [
            path
            for path in paths
            if any(node.node_id not in known_node_ids for node in path.nodes)
        ]
        if not paths:
            return GraphExpandResult(state_id=state.state_id)

        effective_query = request.query.strip()
        if not effective_query:
            raise ValueError("expand query must not be empty")
        ranking = await self._ranking_pipeline.arank(
            RankRequest(
                query=RankQuery(text=effective_query),
                candidates=tuple(
                    RankCandidate(
                        candidate_id=str(index),
                        text=_render_path(path)[0],
                        fields={
                            "nodes": "\n".join(node.label for node in path.nodes),
                            "relations": "\n".join(
                                " ".join(
                                    value
                                    for value in (
                                        edge.relation_type.value,
                                        edge.predicate,
                                    )
                                    if value
                                )
                                for edge in path.edges
                            ),
                        },
                        prior_rank=index + 1,
                    )
                    for index, path in enumerate(paths)
                ),
                top_k=request.max_results,
                candidate_limit=len(paths),
            )
        )
        paths = [paths[int(item.candidate_id)] for item in ranking.ranked]
        evidence_by_edge = await self._verify_path_evidence(paths)

        eligible_paths: list[_EligiblePath] = []
        for path in paths:
            node_evidence = await self._resolve_new_node_evidence(
                path,
                evidence_by_edge,
                known_node_ids,
                request.permission_scope,
            )
            if node_evidence is not None:
                eligible_paths.append(
                    _EligiblePath(path=path, node_evidence=node_evidence)
                )
        if not eligible_paths:
            return GraphExpandResult(state_id=state.state_id)

        # 所有外部读取和 ACL 复查必须在 state 写入前完成；一旦节点进入 state，
        # 本次调用不应再因证据读取失败而留下无响应的半完成结果。
        candidate_evidence: list[PublishedGraphEvidence] = []
        for eligible in eligible_paths:
            for edge in eligible.path.edges:
                candidate_evidence.extend(evidence_by_edge[edge.edge_id])
            for records in eligible.node_evidence.values():
                candidate_evidence.extend(records)
        await self._ensure_sources_readable(
            candidate_evidence,
            request.permission_scope,
        )

        candidate_new_ids = list(
            dict.fromkeys(
                node.node_id
                for eligible in eligible_paths
                for node in eligible.path.nodes
                if node.node_id not in known_node_ids
            )
        )
        try:
            added_node_ids = await self._state_store.add_known_nodes(
                state_id=state.state_id,
                node_ids=candidate_new_ids,
            )
        except NavigationStateMissingError as error:
            raise NavigationStateNotFoundError(state.state_id) from error
        added_node_id_set = set(added_node_ids)
        eligible_paths = [
            eligible
            for eligible in eligible_paths
            if any(
                node.node_id in added_node_id_set for node in eligible.path.nodes
            )
        ]
        if not eligible_paths:
            return GraphExpandResult(state_id=state.state_id)

        nodes_by_id = {
            node.node_id: node
            for eligible in eligible_paths
            for node in eligible.path.nodes
        }
        node_evidence: dict[str, list[PublishedGraphEvidence]] = {}
        for node_id in added_node_ids:
            records = [
                record
                for eligible in eligible_paths
                for record in eligible.node_evidence.get(node_id, [])
            ]
            node_evidence[node_id] = _deduplicate_evidence(records, limit=3)

        retained_evidence: list[PublishedGraphEvidence] = []
        path_views: list[GraphPathView] = []
        for eligible in eligible_paths:
            view, records = _to_path_view(eligible.path, evidence_by_edge)
            path_views.append(view)
            retained_evidence.extend(records)
        for node_id in added_node_ids:
            retained_evidence.extend(node_evidence[node_id])

        evidence_sections = build_graph_evidence_section_views(
            _deduplicate_evidence(retained_evidence)
        )
        return GraphExpandResult(
            state_id=state.state_id,
            discovered_nodes=[
                _to_discovered_node_view(
                    nodes_by_id[node_id],
                    node_evidence[node_id],
                )
                for node_id in added_node_ids
            ],
            paths=path_views,
            evidence_sections=evidence_sections,
        )

    async def _verify_path_evidence(
        self,
        paths: list[TraversedPath],
    ) -> dict[str, list[PublishedGraphEvidence]]:
        edges = {edge.edge_id: edge for path in paths for edge in path.edges}
        return {
            edge.edge_id: await self._evidence_verifier.verify(edge.evidence)
            for edge in edges.values()
        }

    async def _resolve_new_node_evidence(
        self,
        path: TraversedPath,
        evidence_by_edge: dict[str, list[PublishedGraphEvidence]],
        known_node_ids: set[str],
        permission_scope: PermissionScope,
    ) -> dict[str, list[PublishedGraphEvidence]] | None:
        new_nodes = [
            node for node in path.nodes if node.node_id not in known_node_ids
        ]
        mention_node_ids = [
            node.node_id
            for node in new_nodes
            if node.kind is not KnowledgeNodeKind.RESOURCE
        ]
        relation_records = [
            record
            for edge in path.edges
            for record in evidence_by_edge[edge.edge_id]
        ]
        mentions = await self._knowledge_graph.find_mentions(
            node_ids=mention_node_ids,
            resource_ids=sorted(_path_resource_ids(path)),
            preferred_reading_block_ids=list(
                dict.fromkeys(
                    record.evidence.reading_block_id for record in relation_records
                )
            ),
            permission_scope=permission_scope,
            limit_per_node=3,
        )
        mention_records = await self._evidence_verifier.verify(
            [mention.evidence for mention in mentions]
        )
        records_by_node: dict[str, list[PublishedGraphEvidence]] = {}
        for mention, record in zip(mentions, mention_records, strict=True):
            records_by_node.setdefault(mention.node_id, []).append(record)

        for node in new_nodes:
            if node.kind is KnowledgeNodeKind.RESOURCE:
                # Resource 根节点没有 MENTION；它的节点证据只能取与其相连且已经
                # 核验的关系证据，仍然保证调用方能读到对应 ReadingBlock。
                records_by_node[node.node_id] = _deduplicate_evidence(
                    [
                        record
                        for edge in path.edges
                        if node.node_id
                        in (edge.source_node_id, edge.target_node_id)
                        for record in evidence_by_edge[edge.edge_id]
                    ],
                    limit=3,
                )
            if not records_by_node.get(node.node_id):
                return None
        return records_by_node

    async def _filter_readable_paths(
        self,
        paths: list[TraversedPath],
        permission_scope: PermissionScope,
    ) -> list[TraversedPath]:
        """Neo4j 查询后以本地 ACL 事实复查路径涉及的全部资源。"""
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (
                    resource_id
                    for path in paths
                    for resource_id in _path_resource_ids(path)
                ),
                scope=permission_scope,
            )
        )
        return [
            path
            for path in paths
            if _path_resource_ids(path).issubset(readable_resource_ids)
        ]

    async def _ensure_sources_readable(
        self,
        evidence: list[PublishedGraphEvidence],
        permission_scope: PermissionScope,
    ) -> None:
        """state 写入前再核一次证据资源权限，避免提交不可读节点。"""
        resource_ids = list(
            dict.fromkeys(record.evidence.resource_id for record in evidence)
        )
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                resource_ids,
                scope=permission_scope,
            )
        )
        denied = next(
            (
                resource_id
                for resource_id in resource_ids
                if resource_id not in readable_resource_ids
            ),
            None,
        )
        if denied is not None:
            raise GraphAccessRevokedError(denied)


def _to_path_view(
    path: TraversedPath,
    evidence_by_edge: dict[str, list[PublishedGraphEvidence]],
) -> tuple[GraphPathView, list[PublishedGraphEvidence]]:
    """把已核验领域路径投影为关系证据与 ReadingBlock 的交叉引用。"""
    text, relations = _render_path(path)
    retained_records: list[PublishedGraphEvidence] = []
    steps: list[GraphPathStepView] = []

    for edge, relation in zip(path.edges, relations, strict=True):
        records = evidence_by_edge[edge.edge_id]
        retained_records.extend(records)
        steps.append(
            GraphPathStepView(
                relation=relation,
                evidence=[_to_evidence_view(record) for record in records],
            )
        )

    return (
        GraphPathView(
            text=text,
            node_ids=[node.node_id for node in path.nodes],
            steps=steps,
        ),
        retained_records,
    )


def _to_discovered_node_view(
    node: KnowledgeNode,
    evidence: list[PublishedGraphEvidence],
) -> DiscoveredKnowledgeNodeView:
    return DiscoveredKnowledgeNodeView(
        node_id=node.node_id,
        label=node.label,
        kind=node.kind,
        entity_type=node.entity_type,
        evidence=[_to_evidence_view(record) for record in evidence],
    )


def _to_evidence_view(record: PublishedGraphEvidence) -> GraphEvidenceRefView:
    return GraphEvidenceRefView(
        evidence_id=record.evidence.evidence_id,
        resource_id=record.evidence.resource_id,
        reading_block_id=record.evidence.reading_block_id,
        quote=record.evidence.quote,
        range=GraphEvidenceRangeView(
            start_offset=record.block_range.start_offset,
            end_offset=record.block_range.end_offset,
        ),
    )


def _deduplicate_evidence(
    records: list[PublishedGraphEvidence],
    *,
    limit: int | None = None,
) -> list[PublishedGraphEvidence]:
    """按 evidence_id 保留首次出现顺序，并应用调用方给出的条数上限。"""
    result: list[PublishedGraphEvidence] = []
    seen_ids: set[str] = set()
    for record in records:
        evidence_id = record.evidence.evidence_id
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        result.append(record)
        if limit is not None and len(result) >= limit:
            break
    return result


def _render_path(path: TraversedPath) -> tuple[str, list[str]]:
    """按遍历顺序排列节点，同时让箭头始终指向关系事实的 target。"""
    if not path.nodes or len(path.edges) != len(path.nodes) - 1:
        raise RuntimeError("graph path must contain one edge between adjacent nodes")

    parts = [_render_node(path.nodes[0].label)]
    relations: list[str] = []
    for current, following, edge in zip(
        path.nodes[:-1],
        path.nodes[1:],
        path.edges,
        strict=True,
    ):
        relation = _render_relation_type(edge)
        if (
            edge.source_node_id == current.node_id
            and edge.target_node_id == following.node_id
        ):
            parts.extend((f"-{relation}->", _render_node(following.label)))
            source, target = current, following
        elif (
            edge.source_node_id == following.node_id
            and edge.target_node_id == current.node_id
        ):
            parts.extend((f"<-{relation}-", _render_node(following.label)))
            source, target = following, current
        else:
            raise RuntimeError(
                f"graph edge {edge.edge_id} does not connect adjacent path nodes"
            )
        relations.append(
            f"{_render_node(source.label)}-{relation}->{_render_node(target.label)}"
        )
    return "".join(parts), relations


def _render_relation_type(edge: TraversedEdge) -> str:
    if edge.relation_type is not KnowledgeRelationType.RELATED_TO:
        return f"[:{edge.relation_type.value}]"
    if not edge.predicate:
        raise RuntimeError(f"RELATED_TO edge {edge.edge_id} is missing predicate")
    predicate = json.dumps(edge.predicate, ensure_ascii=False)
    return f"[:{edge.relation_type.value} {{predicate: {predicate}}}]"


def _render_node(label: str) -> str:
    return f"({json.dumps(label, ensure_ascii=False)})"


def _path_resource_ids(path: TraversedPath) -> set[str]:
    return {
        *(
            evidence.resource_id
            for edge in path.edges
            for evidence in edge.evidence
        ),
        *(node.resource_id for node in path.nodes if node.resource_id is not None),
    }
