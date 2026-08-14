"""从 navigation state 的已知节点扩展有证据的知识路径。"""

import json
from dataclasses import dataclass, field

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import (
    GraphTraversalRequest,
    KnowledgeRelationType,
    TraversalDirection,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.models.navigation import NavigationStateNotFoundError
from rag.domain.models.provenance import SourceEvidence
from rag.domain.repositories.neo4j import KnowledgeGraphRepository
from rag.domain.repositories.redis.navigation_state_store import NavigationStateStore
from rag.utils.ranking import (
    RankCandidate,
    RankingPipeline,
    RankQuery,
    RankRequest,
)

from .source_evidence_verifier import SourceEvidenceVerifier
from .views import (
    KnowledgeNodeView,
    RetrievedSectionView,
    build_retrieved_section_views,
    to_knowledge_node_view,
)


class UnknownSeedNodeError(RuntimeError):
    """请求的 seed 尚未被当前 navigation state 发现。"""


class GraphAccessRevokedError(RuntimeError):
    """图谱展开期间证据所属资源失去可读权限。"""


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
class GraphExpandResult:
    state_id: str
    discovered_nodes: list[KnowledgeNodeView] = field(default_factory=list)
    paths: list["GraphPathView"] = field(default_factory=list)
    evidence_sections: list[RetrievedSectionView] = field(default_factory=list)


@dataclass(slots=True)
class GraphEvidenceView:
    """一段关系引文及实际包含该引文的权威 SourceRef。"""

    quote: str
    source_ref_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GraphPathStepView:
    """按关系语义方向表达的单步路径及其证据。"""

    relation: str
    evidence: list[GraphEvidenceView] = field(default_factory=list)


@dataclass(slots=True)
class GraphPathView:
    """模型可直接阅读的有向路径，node IDs 只保留作后续导航锚点。"""

    text: str
    node_ids: list[str] = field(default_factory=list)
    steps: list[GraphPathStepView] = field(default_factory=list)


class KnowledgeGraphExpander:
    """编排有界图查询、路径排序、证据核验和状态原子扩展。"""

    def __init__(
        self,
        *,
        knowledge_graph: KnowledgeGraphRepository,
        ranking_pipeline: RankingPipeline,
        evidence_verifier: SourceEvidenceVerifier,
        authorizer: PermissionAuthorizer,
        state_store: NavigationStateStore,
    ) -> None:
        self._knowledge_graph = knowledge_graph
        self._ranking_pipeline = ranking_pipeline
        self._evidence_verifier = evidence_verifier
        self._authorizer = authorizer
        self._state_store = state_store

    async def expand(self, request: GraphExpandRequest) -> GraphExpandResult:
        # 上游 schema 已经保证了 seed、relation 和深度/结果数量边界，这里只处理 state 和可读性边界。
        state = await self._state_store.get(request.state_id)
        if (
            state is None
            or state.user_id != request.permission_scope.user_id
            or state.session_id != request.session_id
        ):
            raise NavigationStateNotFoundError(request.state_id)

        seed_node_ids = request.seed_node_ids
        relation_types = request.relation_types

        known_node_ids = set(state.known_node_ids)
        unknown_seed_ids = [
            node_id for node_id in seed_node_ids if node_id not in known_node_ids
        ]
        if unknown_seed_ids:
            raise UnknownSeedNodeError(unknown_seed_ids[0])

        paths = await self._knowledge_graph.find_paths(
            GraphTraversalRequest(
                seed_node_ids=seed_node_ids,
                permission_scope=request.permission_scope,
                relation_types=relation_types,
                direction=request.direction,
                max_depth=request.max_depth,
                limit=min(request.max_results * 4, 80),
            )
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

        candidate_new_ids = list(
            dict.fromkeys(
                node.node_id
                for path in paths
                for node in path.nodes
                if node.node_id not in known_node_ids
            )
        )
        added_node_ids = await self._state_store.add_known_nodes(
            state_id=state.state_id,
            node_ids=candidate_new_ids,
        )
        added_node_id_set = set(added_node_ids)
        paths = [
            path
            for path in paths
            if any(node.node_id in added_node_id_set for node in path.nodes)
        ]
        if not paths:
            return GraphExpandResult(state_id=state.state_id)

        nodes_by_id = {node.node_id: node for path in paths for node in path.nodes}
        path_views: list[GraphPathView] = []
        retained_evidence: dict[tuple[str, str], SourceEvidence] = {}
        for path in paths:
            path_view, path_evidence = _to_path_view(path, evidence_by_edge)
            path_views.append(path_view)
            for record in path_evidence:
                retained_evidence[
                    (record.revision.resource_id, record.source_ref.ref_id)
                ] = record

        evidence_sections = build_retrieved_section_views(
            list(retained_evidence.values())
        )
        await self._ensure_sources_readable(
            evidence_sections,
            request.permission_scope,
        )
        return GraphExpandResult(
            state_id=state.state_id,
            discovered_nodes=[
                to_knowledge_node_view(nodes_by_id[node_id])
                for node_id in added_node_ids
            ],
            paths=path_views,
            evidence_sections=evidence_sections,
        )

    async def _verify_path_evidence(
        self,
        paths: list[TraversedPath],
    ) -> dict[str, list[SourceEvidence]]:
        edges = {edge.edge_id: edge for path in paths for edge in path.edges}
        records_by_edge: dict[str, list[SourceEvidence]] = {}
        for edge in edges.values():
            records_by_edge[
                edge.edge_id
            ] = await self._evidence_verifier.verify_graph_evidence_refs(
                resource_id=edge.evidence_resource_id,
                content_revision=edge.source_content_revision,
                source_ref_ids=edge.evidence_source_ref_ids,
                quotes=edge.evidence_quotes,
            )
        return records_by_edge

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
        sections: list[RetrievedSectionView],
        permission_scope: PermissionScope,
    ) -> None:
        """返回前再核一次证据所属资源可读，避免读中途 ACL 变化。"""
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (section.resource_id for section in sections),
                scope=permission_scope,
            )
        )
        denied = next(
            (
                section.resource_id
                for section in sections
                if section.resource_id not in readable_resource_ids
            ),
            None,
        )
        if denied is not None:
            raise GraphAccessRevokedError(denied)


def _to_path_view(
    path: TraversedPath,
    evidence_by_edge: dict[str, list[SourceEvidence]],
) -> tuple[GraphPathView, list[SourceEvidence]]:
    """把一条已核验领域路径投影为可读路径，并收紧到实际支撑引文的记录。"""
    text, relations = _render_path(path)
    retained_records: dict[tuple[str, str], SourceEvidence] = {}
    steps: list[GraphPathStepView] = []

    for edge, relation in zip(path.edges, relations, strict=True):
        records = evidence_by_edge[edge.edge_id]
        evidence: list[GraphEvidenceView] = []
        for quote in dict.fromkeys(edge.evidence_quotes):
            matching_records = [
                record for record in records if quote in record.source_text
            ]
            if not matching_records:
                raise RuntimeError(
                    f"verified graph quote is not mapped to edge {edge.edge_id}"
                )
            evidence.append(
                GraphEvidenceView(
                    quote=quote,
                    source_ref_ids=list(
                        dict.fromkeys(
                            record.source_ref.ref_id for record in matching_records
                        )
                    ),
                )
            )
            for record in matching_records:
                retained_records[
                    (record.revision.resource_id, record.source_ref.ref_id)
                ] = record
        steps.append(GraphPathStepView(relation=relation, evidence=evidence))

    return (
        GraphPathView(
            text=text,
            node_ids=[node.node_id for node in path.nodes],
            steps=steps,
        ),
        list(retained_records.values()),
    )


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
        *(edge.evidence_resource_id for edge in path.edges),
        *(node.resource_id for node in path.nodes if node.resource_id is not None),
    }
