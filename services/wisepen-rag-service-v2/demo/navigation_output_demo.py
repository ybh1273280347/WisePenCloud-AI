"""用生产应用算法生成 LOCATE 与 Graph EXPAND 的评审输出。"""

import asyncio
import json
from dataclasses import dataclass, replace
from pathlib import Path

from _demo_documents import (
    DemoDocument,
    build_demo_document,
    flat_text_markdown,
    sectioned_markdown,
)

from rag.api.schemas import CandidateLocateResponse, GraphExpandResponse
from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.navigate import (
    EvidenceVerifier,
    GraphExpandRequest,
    KnowledgeGraphExpander,
    LocateRequest,
    ReadingCandidateLocator,
)
from rag.domain.models.acl import PermissionScope, ResourceAcl
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import (
    KnowledgeEntityType,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.models.navigation import NavigationState
from rag.domain.models.retrieval import RetrievalCandidate
from rag.domain.models.structure import StructureMode
from rag.utils.ranking import RankingPipeline
from rag.utils.ranking.fusion import WeightedRrfFusion
from rag.utils.ranking.rank_gates import (
    HighLowRelevanceGate,
    HighLowRelevanceGateConfig,
)
from rag.utils.ranking.scorers import BM25Scorer
from rag.utils.ranking.tokenizer import JiebaRankingTokenizer


@dataclass(slots=True)
class _EmbeddingResult:
    embeddings: list[list[float]]


class _EmbeddingClient:
    async def aembed(self, values):
        return _EmbeddingResult([[0.31, 0.67] for _ in values])


class _CandidateSearch:
    """代替 Qdrant；返回值仍是生产 RetrievalCandidate。"""

    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        self._candidates = candidates

    async def search(self, request):
        tokens = JiebaRankingTokenizer().tokenize(request.lexical_query)
        ranked = sorted(
            self._candidates,
            key=lambda candidate: sum(
                token in candidate.raw_text for token in tokens if token.strip()
            ),
            reverse=True,
        )
        return [
            replace(
                candidate,
                score=candidate.score
                + sum(
                    token in candidate.raw_text
                    for token in tokens
                    if token.strip()
                ),
            )
            for candidate in ranked[: request.limit]
        ]


class _AclStore:
    async def get_resource_acl(self, resource_id):
        return _acl(resource_id)

    async def get_resource_acls(self, resource_ids):
        return {resource_id: _acl(resource_id) for resource_id in resource_ids}


class _RevisionReader:
    def __init__(self, documents: list[DemoDocument]) -> None:
        self._revisions = {
            document.resource_id: document.revision for document in documents
        }

    async def get_applied_revision(self, resource_id):
        return self._revisions.get(resource_id)


class _EvidenceReader:
    """代替 Mongo 查询；EvidenceVerifier 仍逐字段校验这些权威记录。"""

    def __init__(self, records: list[EvidenceRecord]) -> None:
        self._records = {
            (record.revision.resource_id, record.source_ref.ref_id): record
            for record in records
        }

    async def read_applied_evidence(
        self,
        resource_id,
        content_revision,
        source_ref_ids,
    ):
        records = {
            ref_id: self._records[(resource_id, ref_id)]
            for ref_id in source_ref_ids
            if (resource_id, ref_id) in self._records
        }
        if any(
            record.revision.content_revision != content_revision
            for record in records.values()
        ):
            return None
        return records


class _MentionLookup:
    """代替 Neo4j mention 查询；flat text 按生产规则没有图节点。"""

    async def find_nodes(self, *, evidence, permission_scope, limit):
        if not any(
            record.revision.structure_mode is StructureMode.SECTIONED
            for record in evidence
        ):
            return []
        return [
            KnowledgeNode(
                node_id="kn_demo_surface_water",
                label="表层积水",
                kind=KnowledgeNodeKind.ENTITY,
                entity_type=KnowledgeEntityType.CONCEPT,
            )
        ][:limit]


class _StateStore:
    def __init__(self) -> None:
        self._states: dict[str, NavigationState] = {}

    async def create(self, **kwargs):
        state = NavigationState(
            state_id=f"nav_demo_{len(self._states) + 1}",
            **kwargs,
        )
        self._states[state.state_id] = state
        return state

    async def get(self, state_id):
        return self._states.get(state_id)

    async def add_known_nodes(self, *, state_id, node_ids):
        state = self._states[state_id]
        added = [
            node_id for node_id in node_ids if node_id not in state.known_node_ids
        ]
        state.known_node_ids.extend(added)
        return added


class _Traversal:
    """代替 Neo4j 查询，返回一次 LLM 抽取并发布后的固定图事实。"""

    def __init__(self, path: TraversedPath) -> None:
        self._path = path

    async def find_paths(self, request):
        return [self._path] if "kn_demo_surface_water" in request.seed_node_ids else []


async def main() -> None:
    sectioned = build_demo_document(
        resource_id="demo-rain-garden",
        markdown=sectioned_markdown(),
    )
    flat_text = build_demo_document(
        resource_id="demo-orchard-frost-log",
        markdown=flat_text_markdown(),
    )
    sectioned_phrase = "土壤板结会降低入渗速度"
    flat_phrase = "日出前后最容易出现当夜最低温"
    sectioned_candidate = _candidate_containing(sectioned, sectioned_phrase, 0.93)
    flat_candidate = _candidate_containing(flat_text, flat_phrase, 0.89)
    records = _evidence_records([sectioned, flat_text])
    evidence_verifier = EvidenceVerifier(reader=_EvidenceReader(records))
    state_store = _StateStore()
    authorizer = PermissionAuthorizer(local_store=_AclStore())
    locator = ReadingCandidateLocator(
        embedding_client=_EmbeddingClient(),
        candidate_search=_CandidateSearch([sectioned_candidate, flat_candidate]),
        ranking_pipeline=RankingPipeline(
            fusion=WeightedRrfFusion(),
            gate=HighLowRelevanceGate(
                HighLowRelevanceGateConfig(
                    low_watermark=0.005,
                    high_watermark=0.015,
                    uncertain_limit=2,
                )
            ),
        ),
        authorizer=authorizer,
        evidence_verifier=evidence_verifier,
        mention_lookup=_MentionLookup(),
        revision_reader=_RevisionReader([sectioned, flat_text]),
        state_store=state_store,
    )
    scope = PermissionScope(user_id="demo-reviewer")
    sectioned_result = await locator.locate(
        LocateRequest(
            session_id="demo-session",
            semantic_query="连续降雨后积水迟迟不退，应先检查什么？",
            permission_scope=scope,
            max_results=1,
        )
    )
    flat_result = await locator.locate(
        LocateRequest(
            session_id="demo-session",
            semantic_query="果园为什么在日出前仍要持续监测温度？",
            permission_scope=scope,
            max_results=1,
        )
    )

    graph_quote = "土壤板结会降低入渗速度，并使表层积水消退时间延长。"
    graph_related_quote = "检查时可比较高频踩踏区与封闭区的入渗差异"
    graph_result = await KnowledgeGraphExpander(
        traversal=_Traversal(
            _graph_path(
                document=sectioned,
                source_ref_id=sectioned_candidate.source_ref_id,
                quote=graph_quote,
                related_quote=graph_related_quote,
            )
        ),
        ranking_pipeline=RankingPipeline(
            scorers=(BM25Scorer(tokenizer=JiebaRankingTokenizer()),),
            fusion=WeightedRrfFusion(),
        ),
        evidence_verifier=evidence_verifier,
        authorizer=authorizer,
        state_store=state_store,
    ).expand(
        GraphExpandRequest(
            state_id=sectioned_result.state_id,
            session_id="demo-session",
            permission_scope=scope,
            seed_node_ids=["kn_demo_surface_water"],
            query="哪些因素会延长积水消退时间？",
        )
    )

    sectioned_payload = CandidateLocateResponse.model_validate(
        sectioned_result
    ).model_dump(mode="json", exclude_none=True)
    flat_payload = CandidateLocateResponse.model_validate(flat_result).model_dump(
        mode="json",
        exclude_none=True,
    )
    graph_payload = GraphExpandResponse.model_validate(graph_result).model_dump(
        mode="json",
        exclude_none=True,
    )
    _assert_contracts(
        sectioned_payload=sectioned_payload,
        flat_payload=flat_payload,
        graph_payload=graph_payload,
        sectioned_phrase=sectioned_phrase,
        flat_phrase=flat_phrase,
        graph_quote=graph_quote,
        graph_related_quote=graph_related_quote,
    )
    _write_outputs(
        sectioned=sectioned,
        flat_text=flat_text,
        sectioned_payload=sectioned_payload,
        flat_payload=flat_payload,
        graph_payload=graph_payload,
        graph_quote=graph_quote,
        graph_related_quote=graph_related_quote,
    )


def _candidate_containing(
    document: DemoDocument,
    phrase: str,
    score: float,
) -> RetrievalCandidate:
    chunk = next(
        chunk for chunk in document.retrieval_chunks if phrase in chunk.raw_text
    )
    source_ref = next(
        ref for ref in document.source_refs if ref.chunk_id == chunk.chunk_id
    )
    return RetrievalCandidate(
        chunk_id=chunk.chunk_id,
        reading_block_id=chunk.reading_block_id,
        section_id=chunk.section_id,
        section_path=list(chunk.section_path),
        resource_id=document.resource_id,
        content_revision=document.revision.content_revision,
        raw_text=chunk.raw_text,
        source_spans=list(chunk.source_spans),
        page_labels=list(chunk.page_labels),
        anchor_labels=list(chunk.anchor_labels),
        source_ref_id=source_ref.ref_id,
        score=score,
    )


def _evidence_records(documents: list[DemoDocument]) -> list[EvidenceRecord]:
    records = []
    for document in documents:
        chunks_by_id = {
            chunk.chunk_id: chunk for chunk in document.retrieval_chunks
        }
        blocks_by_id = {
            block.block_id: block for block in document.reading_blocks
        }
        sections_by_id = {
            section.section_id: section for section in document.sections
        }
        for source_ref in document.source_refs:
            chunk = chunks_by_id[source_ref.chunk_id]
            records.append(
                EvidenceRecord(
                    revision=document.revision,
                    source_ref=source_ref,
                    reading_block=blocks_by_id[source_ref.reading_block_id],
                    section=sections_by_id[source_ref.section_id],
                    source_text=chunk.raw_text,
                )
            )
    return records


def _graph_path(
    *,
    document: DemoDocument,
    source_ref_id: str,
    quote: str,
    related_quote: str,
) -> TraversedPath:
    return TraversedPath(
        nodes=[
            KnowledgeNode(
                node_id="kn_demo_surface_water",
                label="表层积水",
                kind=KnowledgeNodeKind.ENTITY,
                entity_type=KnowledgeEntityType.CONCEPT,
            ),
            KnowledgeNode(
                node_id="kn_demo_soil_compaction",
                label="土壤板结",
                kind=KnowledgeNodeKind.ENTITY,
                entity_type=KnowledgeEntityType.CONCEPT,
            ),
            KnowledgeNode(
                node_id="kn_demo_high_traffic_area",
                label="高频踩踏区",
                kind=KnowledgeNodeKind.ENTITY,
                entity_type=KnowledgeEntityType.CONCEPT,
            ),
        ],
        edges=[
            TraversedEdge(
                edge_id="ke_demo_compaction_delays_infiltration",
                source_node_id="kn_demo_soil_compaction",
                target_node_id="kn_demo_surface_water",
                relation_type=KnowledgeRelationType.CAUSES,
                evidence_resource_id=document.resource_id,
                source_content_revision=document.revision.content_revision,
                evidence_quotes=[quote],
                evidence_source_ref_ids=[source_ref_id],
            ),
            TraversedEdge(
                edge_id="ke_demo_compaction_common_in_traffic_area",
                source_node_id="kn_demo_soil_compaction",
                target_node_id="kn_demo_high_traffic_area",
                relation_type=KnowledgeRelationType.RELATED_TO,
                predicate="常见于",
                evidence_resource_id=document.resource_id,
                source_content_revision=document.revision.content_revision,
                evidence_quotes=[related_quote],
                evidence_source_ref_ids=[source_ref_id],
            ),
        ],
    )


def _assert_contracts(
    *,
    sectioned_payload,
    flat_payload,
    graph_payload,
    sectioned_phrase,
    flat_phrase,
    graph_quote,
    graph_related_quote,
) -> None:
    assert sectioned_phrase in sectioned_payload["sections"][0]["reading_blocks"][0]["text"]
    assert flat_phrase in flat_payload["sections"][0]["reading_blocks"][0]["text"]
    assert set(flat_payload["sections"][0]) == {
        "resource_id",
        "section_id",
        "title",
        "section_path",
        "reading_blocks",
    }
    assert "page_range" not in flat_payload["sections"][0]["reading_blocks"][0]
    assert flat_payload["nodes"] == []
    assert set(sectioned_payload["sections"][0]) == {
        "resource_id",
        "section_id",
        "title",
        "section_path",
        "reading_blocks",
    }
    assert graph_payload["discovered_nodes"] == [
        {
            "node_id": "kn_demo_soil_compaction",
            "label": "土壤板结",
            "kind": "Entity",
            "entity_type": "concept",
        },
        {
            "node_id": "kn_demo_high_traffic_area",
            "label": "高频踩踏区",
            "kind": "Entity",
            "entity_type": "concept",
        },
    ]
    assert graph_payload["paths"][0]["text"] == (
        '("表层积水")<-[:CAUSES]-("土壤板结")'
        '-[:RELATED_TO {predicate: "常见于"}]->("高频踩踏区")'
    )
    assert graph_payload["paths"][0]["node_ids"] == [
        "kn_demo_surface_water",
        "kn_demo_soil_compaction",
        "kn_demo_high_traffic_area",
    ]
    assert graph_payload["paths"][0]["steps"] == [
        {
            "relation": '("土壤板结")-[:CAUSES]->("表层积水")',
            "evidence": [
                {
                    "quote": graph_quote,
                    "source_ref_ids": [
                        sectioned_payload["sections"][0]["reading_blocks"][0][
                            "matches"
                        ][0]["source_ref_id"]
                    ],
                }
            ],
        },
        {
            "relation": (
                '("土壤板结")-[:RELATED_TO {predicate: "常见于"}]'
                '->("高频踩踏区")'
            ),
            "evidence": [
                {
                    "quote": graph_related_quote,
                    "source_ref_ids": [
                        sectioned_payload["sections"][0]["reading_blocks"][0][
                            "matches"
                        ][0]["source_ref_id"]
                    ],
                }
            ],
        },
    ]
    assert graph_payload["evidence_sections"] == sectioned_payload["sections"]
    assert "nodes" not in graph_payload
    assert "edges" not in graph_payload
    assert "sources" not in graph_payload


def _write_outputs(
    *,
    sectioned,
    flat_text,
    sectioned_payload,
    flat_payload,
    graph_payload,
    graph_quote,
    graph_related_quote,
) -> None:
    directory = Path(__file__).parent
    locate_output = "\n".join(
        [
            "=== Review notes ===",
            "- 文档先经过真实 Section/ReadingBlock/RetrievalChunk/SourceRef 构造链。",
            "- embedding 与 Qdrant 召回用确定性 fake；WeightedRRF、相关性 gate、ACL、revision 过滤、VERIFY 和提升算法使用生产实现。",
            "- sectioned 与 flat text 都从 RetrievalChunk 命中提升为完整 ReadingBlock。",
            "- flat text 不抽取知识图，因此 nodes 为空，但仍可作为确定性 Section READ 锚点。",
            "",
            "=== SECTIONED source text ===",
            sectioned.markdown,
            "=== SECTIONED locate ===",
            json.dumps(sectioned_payload, ensure_ascii=False, indent=2),
            "",
            "=== FLAT_TEXT source text ===",
            flat_text.markdown,
            "=== FLAT_TEXT locate ===",
            json.dumps(flat_payload, ensure_ascii=False, indent=2),
        ]
    )
    graph_output = "\n".join(
        [
            "=== Review notes ===",
            "- Neo4j traversal 和 LLM 图谱抽取结果用固定 demo ID/type 表示。",
            "- seed 校验、BM25/WeightedRRF 路径排序、EvidenceVerifier quote 核验、状态扩展和 ReadingBlock 回补使用生产实现。",
            "- flat text 在生产索引阶段跳过图谱抽取，因此没有伪造 expandGraph 结果。",
            "",
            "=== Simulated extracted graph fact ===",
            f"quote: {graph_quote}",
            f"quote: {graph_related_quote}",
            "entity anchors: kn_demo_surface_water, kn_demo_soil_compaction, kn_demo_high_traffic_area",
            "relations:",
            "  (\"土壤板结\")-[:CAUSES]->(\"表层积水\")",
            "  (\"土壤板结\")-[:RELATED_TO {predicate: \"常见于\"}]->(\"高频踩踏区\")",
            "",
            "=== SECTIONED expandGraph ===",
            json.dumps(graph_payload, ensure_ascii=False, indent=2),
            "",
            "=== FLAT_TEXT graph behavior ===",
            "structure_mode: flat_text",
            "graph extraction: skipped",
            "expandGraph: not applicable",
        ]
    )
    locate_path = directory / "locate_demo_output.txt"
    graph_path = directory / "graph_expand_demo_output.txt"
    locate_path.write_text(locate_output, encoding="utf-8")
    graph_path.write_text(graph_output, encoding="utf-8")
    print(locate_path)
    print(graph_path)


def _acl(resource_id: str) -> ResourceAcl:
    return ResourceAcl(
        resource_id=resource_id,
        acl_revision=1,
        owner_id="demo-reviewer",
    )


if __name__ == "__main__":
    asyncio.run(main())
