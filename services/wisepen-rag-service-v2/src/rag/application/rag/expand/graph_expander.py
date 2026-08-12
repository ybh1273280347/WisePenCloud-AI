"""从 navigation state 的已知节点扩展有证据的知识路径。"""

from dataclasses import dataclass, field

from rag.domain.graph_traversal import (
    GraphTraversalRequest,
    TraversalDirection,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.acl import PermissionScope
from rag.domain.evidence import EvidenceRecord
from rag.domain.knowledge_graph import KnowledgeNode, KnowledgeRelationType
from rag.domain.navigation import NavigationStateNotFoundError
from rag.domain.repositories.graph_traversal import GraphTraversal
from rag.domain.repositories.navigation_state_store import NavigationStateStore
from rag.utils.ranking import (
    RankCandidate,
    RankingPipeline,
    RankQuery,
    RankRequest,
)

from rag.application.rag.verify import EvidenceVerifier


class UnknownSeedNodeError(RuntimeError):
    """请求的 seed 尚未被当前 navigation state 发现。"""


@dataclass(slots=True)
class GraphExpandRequest:
    state_id: str
    session_id: str
    permission_scope: PermissionScope
    seed_node_ids: list[str]
    relation_types: list[KnowledgeRelationType] = field(default_factory=list)
    direction: TraversalDirection = TraversalDirection.BOTH
    max_depth: int = 1
    max_results: int = 10
    query: str | None = None


@dataclass(slots=True)
class GraphExpandResult:
    state_id: str
    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[TraversedEdge] = field(default_factory=list)
    paths: list[TraversedPath] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)


class KnowledgeGraphExpander:
    """编排有界图查询、路径排序、证据核验和状态原子扩展。"""

    def __init__(
        self,
        *,
        traversal: GraphTraversal,
        ranking_pipeline: RankingPipeline,
        evidence_verifier: EvidenceVerifier,
        state_store: NavigationStateStore,
    ) -> None:
        self._traversal = traversal
        self._ranking_pipeline = ranking_pipeline
        self._evidence_verifier = evidence_verifier
        self._state_store = state_store

    async def expand(self, request: GraphExpandRequest) -> GraphExpandResult:
        state = await self._state_store.get(request.state_id)
        if (
            state is None
            or state.user_id != request.permission_scope.user_id
            or state.session_id != request.session_id
        ):
            raise NavigationStateNotFoundError(request.state_id)

        seed_node_ids = list(dict.fromkeys(request.seed_node_ids))
        relation_types = list(dict.fromkeys(request.relation_types))
        if not 1 <= len(seed_node_ids) <= 16:
            raise ValueError("expand requires 1 to 16 seed nodes")
        if len(relation_types) > 16:
            raise ValueError("expand accepts at most 16 relation types")
        if request.max_depth not in (1, 2):
            raise ValueError("expand max_depth must be 1 or 2")
        if not 1 <= request.max_results <= 20:
            raise ValueError("expand max_results must be between 1 and 20")

        known_node_ids = set(state.known_node_ids)
        unknown_seed_ids = [
            node_id for node_id in seed_node_ids if node_id not in known_node_ids
        ]
        if unknown_seed_ids:
            raise UnknownSeedNodeError(unknown_seed_ids[0])

        paths = await self._traversal.find_paths(
            GraphTraversalRequest(
                seed_node_ids=seed_node_ids,
                permission_scope=request.permission_scope,
                relation_types=relation_types,
                direction=request.direction,
                max_depth=request.max_depth,
                limit=min(request.max_results * 4, 80),
            )
        )
        paths = [
            path
            for path in paths
            if any(node.node_id not in known_node_ids for node in path.nodes)
        ]
        if not paths:
            return GraphExpandResult(state_id=state.state_id)

        effective_query = (request.query or state.root_query).strip()
        if not effective_query:
            raise ValueError("expand query and state root query are both empty")
        ranking = await self._ranking_pipeline.arank(
            RankRequest(
                query=RankQuery(text=effective_query),
                candidates=tuple(
                    RankCandidate(
                        candidate_id=str(index),
                        text=_path_text(path),
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
        evidence = await self._verify_path_evidence(paths)

        candidate_new_ids = list(
            dict.fromkeys(
                node.node_id
                for path in paths
                for node in path.nodes
                if node.node_id not in known_node_ids
            )
        )
        added_node_ids = set(
            await self._state_store.add_known_nodes(
                state_id=state.state_id,
                node_ids=candidate_new_ids,
            )
        )
        paths = [
            path
            for path in paths
            if any(node.node_id in added_node_ids for node in path.nodes)
        ]
        if not paths:
            return GraphExpandResult(state_id=state.state_id)

        nodes_by_id = {node.node_id: node for path in paths for node in path.nodes}
        edges_by_id = {edge.edge_id: edge for path in paths for edge in path.edges}
        retained_evidence = {
            (edge.evidence_resource_id, source_ref_id)
            for edge in edges_by_id.values()
            for source_ref_id in edge.evidence_source_ref_ids
        }
        return GraphExpandResult(
            state_id=state.state_id,
            nodes=[nodes_by_id[node_id] for node_id in sorted(nodes_by_id)],
            edges=[edges_by_id[edge_id] for edge_id in sorted(edges_by_id)],
            paths=paths,
            evidence=[
                record
                for record in evidence
                if (
                    record.revision.resource_id,
                    record.source_ref.ref_id,
                )
                in retained_evidence
            ],
        )

    async def _verify_path_evidence(
        self,
        paths: list[TraversedPath],
    ) -> list[EvidenceRecord]:
        edges = {edge.edge_id: edge for path in paths for edge in path.edges}
        records: dict[tuple[str, str], EvidenceRecord] = {}
        for edge in edges.values():
            verified = await self._evidence_verifier.verify_refs(
                resource_id=edge.evidence_resource_id,
                content_revision=edge.source_content_revision,
                source_ref_ids=edge.evidence_source_ref_ids,
                quotes=edge.evidence_quotes,
            )
            for record in verified:
                records[(record.revision.resource_id, record.source_ref.ref_id)] = record
        return list(records.values())


def _path_text(path: TraversedPath) -> str:
    nodes = " -> ".join(node.label for node in path.nodes)
    relations = "\n".join(
        " | ".join(
            value
            for value in (edge.relation_type.value, edge.predicate)
            if value
        )
        for edge in path.edges
    )
    return f"Path: {nodes}\nRelations:\n{relations}"
