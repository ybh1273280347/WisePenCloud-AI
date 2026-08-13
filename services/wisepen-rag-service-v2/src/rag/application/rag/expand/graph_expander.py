"""从 navigation state 的已知节点扩展有证据的知识路径。"""

from dataclasses import dataclass, field

from rag.domain.models.graph import (
    GraphTraversalRequest,
    TraversalDirection,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.models.acl import PermissionScope
from rag.domain.models.content import SectionView
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import KnowledgeNode, KnowledgeRelationType
from rag.domain.models.navigation import NavigationStateNotFoundError
from rag.domain.models.navigation import KnownSection
from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.repositories.mongo.readers.applied_content import AppliedContentReader
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.neo4j.graph_traversal import GraphTraversal
from rag.domain.repositories.redis.navigation_state_store import NavigationStateStore
from rag.utils.ranking import (
    RankCandidate,
    RankingPipeline,
    RankQuery,
    RankRequest,
)

from rag.application.rag.verify import (
    EvidenceCorruptError,
    EvidenceRevisionError,
    EvidenceVerifier,
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
    sources: list[SectionView] = field(default_factory=list)


class KnowledgeGraphExpander:
    """编排有界图查询、路径排序、证据核验和状态原子扩展。"""

    def __init__(
        self,
        *,
        traversal: GraphTraversal,
        ranking_pipeline: RankingPipeline,
        evidence_verifier: EvidenceVerifier,
        authorizer: PermissionAuthorizer,
        content_reader: AppliedContentReader,
        revision_reader: AppliedRevisionReader,
        state_store: NavigationStateStore,
    ) -> None:
        self._traversal = traversal
        self._ranking_pipeline = ranking_pipeline
        self._evidence_verifier = evidence_verifier
        self._authorizer = authorizer
        self._content_reader = content_reader
        self._revision_reader = revision_reader
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
        sources = await self._build_source_views(
            [
                record
                for record in evidence
                if (
                    record.revision.resource_id,
                    record.source_ref.ref_id,
                )
                in retained_evidence
            ]
        )
        await self._ensure_sources_readable(sources, request.permission_scope)
        await self._state_store.add_known_sections(
            state_id=state.state_id,
            sections=_known_sections(sources),
        )
        return GraphExpandResult(
            state_id=state.state_id,
            nodes=[nodes_by_id[node_id] for node_id in sorted(nodes_by_id)],
            edges=[edges_by_id[edge_id] for edge_id in sorted(edges_by_id)],
            paths=paths,
            sources=sources,
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

    async def _build_source_views(
        self,
        evidence: list[EvidenceRecord],
    ) -> list[SectionView]:
        """把图谱证据还原成可继续阅读的 SectionView。

        v1 的 cypher 返回的是 evidence 所在 Section 的阅读上下文和标题树
        frontier，而不是孤立证据片段。这里在 VERIFY 之后回读 Section 内容，
        让 graph expand 发现的证据也能进入后续标题树探索。
        """
        records_by_section: dict[tuple[str, str], list[EvidenceRecord]] = {}
        expected_revisions: dict[str, str] = {}
        section_order: list[tuple[str, str]] = []
        for record in evidence:
            resource_id = record.revision.resource_id
            expected_revision = expected_revisions.setdefault(
                resource_id,
                record.revision.content_revision,
            )
            if expected_revision != record.revision.content_revision:
                raise EvidenceRevisionError(resource_id)

            key = (resource_id, record.section.section_id)
            if key not in records_by_section:
                section_order.append(key)
            records_by_section.setdefault(key, []).append(record)

        views_by_key: dict[tuple[str, str], SectionView] = {}
        for resource_id in dict.fromkeys(resource_id for resource_id, _ in section_order):
            revision = await self._revision_reader.get_applied_revision(resource_id)
            if (
                revision is None
                or revision.content_revision != expected_revisions[resource_id]
            ):
                raise EvidenceRevisionError(resource_id)

            section_ids = [
                section_id
                for item_resource_id, section_id in section_order
                if item_resource_id == resource_id
            ]
            contents = await self._content_reader.get_applied_sections(
                resource_id,
                section_ids,
            )
            if contents is None:
                raise EvidenceRevisionError(resource_id)

            # Section 内容读取期间 revision 可能切换，返回前再次校验，避免旧证据配新正文。
            revision = await self._revision_reader.get_applied_revision(resource_id)
            if (
                revision is None
                or revision.content_revision != expected_revisions[resource_id]
            ):
                raise EvidenceRevisionError(resource_id)

            for section_id in section_ids:
                content = contents.get(section_id)
                if content is None:
                    raise EvidenceCorruptError(
                        f"graph evidence section {section_id} is absent"
                    )
                key = (resource_id, section_id)
                views_by_key[key] = SectionView(
                    resource_id=resource_id,
                    content_revision=expected_revisions[resource_id],
                    section=content.section,
                    reading_blocks=content.reading_blocks,
                    frontier=content.frontier,
                    evidence=records_by_section[key],
                )

        return [views_by_key[key] for key in section_order]

    async def _ensure_sources_readable(
        self,
        sources: list[SectionView],
        permission_scope: PermissionScope,
    ) -> None:
        """返回前再核一次证据所属资源可读，避免读中途 ACL 变化。"""
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (source.resource_id for source in sources),
                scope=permission_scope,
            )
        )
        denied = next(
            (
                source.resource_id
                for source in sources
                if source.resource_id not in readable_resource_ids
            ),
            None,
        )
        if denied is not None:
            raise GraphAccessRevokedError(denied)


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


def _known_sections(sources: list[SectionView]) -> dict[str, KnownSection]:
    known: dict[str, KnownSection] = {}
    for source in sources:
        for section in (
            source.section,
            source.frontier.parent,
            source.frontier.previous,
            source.frontier.next,
            *source.frontier.children,
        ):
            if section is not None:
                known[section.section_id] = KnownSection(
                    resource_id=source.resource_id,
                    content_revision=source.content_revision,
                )
    return known
