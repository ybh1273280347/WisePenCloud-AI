from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

ranking_engine_path = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "chat"
    / "application"
    / "utils"
    / "ranking_engine"
)
ranking_engine_package = types.ModuleType("chat.application.utils.ranking_engine")
ranking_engine_package.__path__ = [str(ranking_engine_path)]
sys.modules["chat.application.utils.ranking_engine"] = ranking_engine_package

scorers_package = types.ModuleType("chat.application.utils.ranking_engine.scorers")
scorers_package.__path__ = [str(ranking_engine_path / "scorers")]
sys.modules["chat.application.utils.ranking_engine.scorers"] = scorers_package

registry_module = types.ModuleType("chat.application.utils.ranking_engine.registry")
registry_module.get_ranking_engine = lambda name: None
sys.modules["chat.application.utils.ranking_engine.registry"] = registry_module


class _Settings:
    ZERO_ENTROPY_API_KEY = "test-zero-entropy-key"
    EVIDENCE_RANKER_ZE_MODEL = "test-rerank-model"
    EVIDENCE_RANKER_ZE_TOP_N = 20
    QUERY_MODEL = "test-query-model"


config_module = types.ModuleType("chat.core.config.app_settings")
config_module.settings = _Settings()
sys.modules["chat.core.config.app_settings"] = config_module

from chat.application.rag.answerability import (  # noqa: E402
    AnswerabilityHardGate,
    AnswerabilitySoftGate,
    RagAnswerabilityInput,
    RagAnswerabilityWarningReason,
    RagHardGateReason,
)
from chat.application.rag.ranking import (  # noqa: E402
    RagEvidenceRankingRequest,
    RagEvidenceRankingService,
)
from chat.application.rag.context_builder import (  # noqa: E402
    RagContextBuilder,
    RagEvidenceMaterializeRequest,
    RagEvidenceMaterializer,
)
from chat.application.rag.retrieval import (  # noqa: E402
    RagExactFilter,
    RagPermissionScope,
    RagRetrievalChannel,
    RagRetrievalProfile,
    ScoredChunk,
)
from chat.application.rag.retrieval.retrievers import RagHybridRetriever  # noqa: E402
from chat.application.rag.knowledge_search import (  # noqa: E402
    RagKnowledgeSearcher,
    RagKnowledgeSearchRequest,
)
from chat.application.rag.kafka_consumers.document_ready_consumer import (  # noqa: E402
    DocumentReadyMessageError,
    RagDocumentReadyConsumer,
)
from chat.application.rag.acl import RagResourceAclProjection  # noqa: E402
from chat.application.rag.ingestion import (  # noqa: E402
    ContextIndexingInput,
    ContextIndexingResult,
    RagChildChunk,
    RagChunkExtraIndex,
    RagChunkingService,
    RagChunkingResult,
    RagMarkdownIngestionPayload,
    RagParentChunk,
)
from chat.application.rag.ingestion.ingester import (  # noqa: E402
    RagMarkdownIngester,
    RagMarkdownIngestResult,
)
from chat.application.utils.chunking_engine.models import IndexKind  # noqa: E402
from chat.application.utils.ranking_engine.models import (  # noqa: E402
    RankCandidate,
    RankedCandidate,
)
from chat.application.utils.ranking_engine.engine import RankingEngine  # noqa: E402
from chat.application.utils.ranking_engine.pipeline import RankingPipeline  # noqa: E402


def _ranking_engine_without_reranker() -> RankingEngine:
    return RankingEngine(
        pipeline=RankingPipeline(
            name="test.rag.knowledge_search",
        )
    )


def test_chunking_service_produces_parent_and_child_chunks() -> None:
    page_one = "请求必须携带 AppBuilder API Key。 " * 120
    page_two = "POST /v2/ai_search/web_search 使用 Bearer token。 " * 120
    payload = RagMarkdownIngestionPayload(
        resource_id="resource-auth",
        document_version="v1",
        markdown="\n\n".join(
            [
                "<!-- page 1 -->",
                "# 鉴权",
                page_one,
                "<!-- page 2 -->",
                "## 接口",
                page_two,
            ]
        ),
    )

    result = RagChunkingService().chunk_payload(payload)

    assert result.resource_id == "resource-auth"
    assert result.document_version == "v1"
    assert result.pipeline == "parent_child_markdown"
    assert result.parent_chunks
    assert result.child_chunks
    assert all(isinstance(chunk, RagParentChunk) for chunk in result.parent_chunks)
    assert all(isinstance(chunk, RagChildChunk) for chunk in result.child_chunks)
    assert all(chunk.parent_chunk_id for chunk in result.child_chunks)


def test_chunking_service_persists_extra_indexes_for_evidence_location() -> None:
    markdown = "\n\n".join(
        [
            "<!-- page 1 -->",
            "# 鉴权",
            "请求必须携带 AppBuilder API Key。 " * 120,
            "<!-- page 2 -->",
            "## 接口",
            "POST /v2/ai_search/web_search 使用 Bearer token。 " * 120,
        ]
    )

    result = RagChunkingService().chunk(
        markdown=markdown,
    )

    all_extra_indexes = tuple(
        extra_index
        for chunk in (*result.parent_chunks, *result.child_chunks)
        for extra_index in chunk.extra_indexes
    )
    assert all_extra_indexes
    assert {index.index_name for index in all_extra_indexes} >= {"page:1", "page:2"}

    page_one = next(index for index in all_extra_indexes if index.index_name == "page:1")
    page_two = next(index for index in all_extra_indexes if index.index_name == "page:2")
    assert page_one.index_kind == IndexKind.PAGE
    assert page_two.index_kind == IndexKind.PAGE
    assert page_one.start_offset == 0
    assert page_one.end_offset is not None
    assert page_two.start_offset == page_one.end_offset

    page_one_chunks = [
        chunk
        for chunk in result.child_chunks
        if any(extra_index.index_name == "page:1" for extra_index in chunk.extra_indexes)
    ]
    assert page_one_chunks
    assert all(chunk.page_label == "1" for chunk in page_one_chunks)
    assert all(chunk.start_offset is not None for chunk in page_one_chunks)
    assert all(chunk.end_offset is not None for chunk in page_one_chunks)


@pytest.mark.anyio
async def test_document_ready_ingestion_maps_kafka_payload_to_rag_payload() -> None:
    ingestion_service = _RecordingIngestionService()
    service = RagDocumentReadyConsumer(
        ingester=ingestion_service,
    )

    await service.handle(
        {
            "resourceId": "resource-doc",
            "version": 3,
            "content": "# 标题\n\n正文内容",
        }
    )

    assert ingestion_service.payload is not None
    assert ingestion_service.payload.resource_id == "resource-doc"
    assert ingestion_service.payload.document_version == "3"
    assert ingestion_service.payload.markdown == "# 标题\n\n正文内容"


@pytest.mark.anyio
async def test_rag_ingestion_indexes_corpus_qdrant_and_elastic_with_acl_projection() -> None:
    parent = RagParentChunk(
        chunk_id="parent-1",
        text="父块说明 API 鉴权要求。",
        chunk_index=0,
    )
    child = RagChildChunk(
        chunk_id="child-1",
        text="请求必须携带 Authorization header。",
        chunk_index=1,
        parent_chunk_id="parent-1",
    )
    acl_projection = RagResourceAclProjection(
        resource_id="resource-doc",
        owner_id="owner-1",
    )
    corpus_repository = _RecordingCorpusRepository()
    qdrant_repository = _RecordingIndexRepository()
    elastic_repository = _RecordingIndexRepository()
    service = RagMarkdownIngester(
        chunking_service=_PreparedChunkingService(
            RagChunkingResult(
                parent_chunks=(parent,),
                child_chunks=(child,),
                pipeline="test",
                resource_id="resource-doc",
                document_version="3",
            )
        ),
        context_indexing_service=_RecordingContextIndexingService(),
        embedding_client=_RecordingEmbeddingClient(),
        corpus_repository=corpus_repository,
        acl_repository=_RecordingAclRepository(acl_projection),
        qdrant_repository=qdrant_repository,
        elastic_repository=elastic_repository,
    )

    result = await service.ingest_markdown(
        RagMarkdownIngestionPayload(
            resource_id="resource-doc",
            document_version="3",
            markdown="# 鉴权\n\n请求必须携带 Authorization header。",
        )
    )

    assert result.indexed_child_count == 1
    assert result.acl_projection == acl_projection
    assert corpus_repository.saved is not None
    assert corpus_repository.saved.child_chunks[0].indexing_context == "该片段说明 API 鉴权请求头要求。"
    assert qdrant_repository.upsert_calls[0]["dense_vectors"] == {"child-1": [0.1, 0.2]}
    assert "sparse_vectors" not in qdrant_repository.upsert_calls[0]
    assert qdrant_repository.upsert_calls[0]["acl_projection"] == acl_projection
    assert elastic_repository.upsert_calls[0]["child_chunks"][0].indexing_text
    assert elastic_repository.upsert_calls[0]["acl_projection"] == acl_projection


@pytest.mark.anyio
async def test_knowledge_search_runs_elastic_scope_qdrant_bm25_ranking_and_gates() -> None:
    qdrant_repository = _RecordingRetrievalRepository(
        chunks=(
            ScoredChunk(
                chunk_id="child-1",
                text="请求必须携带 AppBuilder API Key。",
                retrieval_score=0.91,
                retrieval_rank=1,
                resource_id="resource-doc",
                document_version="3",
                corpus_version="3",
                parent_chunk_id="parent-1",
                page_label="1",
                section_path=("鉴权",),
                retrieval_channels=(
                    RagRetrievalChannel.DENSE,
                    RagRetrievalChannel.SPARSE,
                ),
            ),
        )
    )
    soft_gate = _RecordingSoftGate()
    service = RagKnowledgeSearcher(
        retriever=RagHybridRetriever(
            embedding_client=_RecordingEmbeddingClient(),
            elastic_retriever=_RecordingElasticRepository(candidate_chunk_ids=("child-1",)),
            qdrant_retriever=qdrant_repository,
        ),
        ranking_service=_RecordingRankingService(),
        hard_gate=AnswerabilityHardGate(),
        soft_gate=soft_gate,
        evidence_materializer=RagEvidenceMaterializer(
            corpus_repository=_RecordingCorpusRepository()
        ),
        context_builder=RagContextBuilder(),
    )

    result = await service.search(
        RagKnowledgeSearchRequest(
            query="AppBuilder API Key",
            resource_id="resource-doc",
            corpus_version="3",
            retrieval_profile=RagRetrievalProfile.ANCHORED_EXACT,
            exact_filter=RagExactFilter(required_phrases=("API Key",)),
            permission_scope=RagPermissionScope(
                user_id="user-1",
                group_role_map={"group-1": "MEMBER"},
            ),
            top_k=1,
            candidate_limit=10,
        )
    )

    retrieval_request = qdrant_repository.retrieve_calls[0]
    assert retrieval_request.candidate_chunk_ids == ("child-1",)
    assert retrieval_request.query_text == "AppBuilder API Key"
    assert retrieval_request.permission_scope is not None
    assert result.should_continue
    assert result.elastic_candidate_chunk_ids == ("child-1",)
    assert result.ranked[0].candidate_id == "child-1"
    assert result.direct_evidence[0].citation_id == "E1"
    assert result.direct_evidence[0].citation_anchor == "p.1 | 鉴权"
    assert result.context is not None
    assert "AppBuilder API Key" in result.context.context_text
    assert soft_gate.calls


@pytest.mark.anyio
async def test_knowledge_search_stops_when_elastic_strict_prefilter_is_empty() -> None:
    qdrant_repository = _RecordingRetrievalRepository()
    service = RagKnowledgeSearcher(
        retriever=RagHybridRetriever(
            embedding_client=_RecordingEmbeddingClient(),
            elastic_retriever=_RecordingElasticRepository(candidate_chunk_ids=()),
            qdrant_retriever=qdrant_repository,
        ),
        ranking_service=_RecordingRankingService(),
        hard_gate=AnswerabilityHardGate(),
        soft_gate=_RecordingSoftGate(),
        evidence_materializer=RagEvidenceMaterializer(
            corpus_repository=_RecordingCorpusRepository()
        ),
        context_builder=RagContextBuilder(),
    )

    result = await service.search(
        RagKnowledgeSearchRequest(
            query="不存在的锚点",
            resource_id="resource-doc",
            corpus_version="3",
            retrieval_profile=RagRetrievalProfile.ANCHORED_EXACT,
            exact_filter=RagExactFilter(required_phrases=("不存在的锚点",)),
        )
    )

    assert qdrant_repository.retrieve_calls == []
    assert not result.should_continue
    assert result.hard_gate.reason == RagHardGateReason.EMPTY_RETRIEVAL


@pytest.mark.anyio
async def test_evidence_materializer_uses_mongo_child_and_parent_context() -> None:
    parent = RagParentChunk(
        chunk_id="parent-1",
        text="父块完整上下文，包含鉴权接口和调用限制。",
        chunk_index=0,
    )
    child = RagChildChunk(
        chunk_id="child-1",
        text="子块原文：必须携带 AppBuilder API Key。",
        chunk_index=1,
        parent_chunk_id="parent-1",
        extra_indexes=(
            RagChunkExtraIndex(
                index_name="page:2",
                index_kind=IndexKind.PAGE,
                page_label="2",
            ),
            RagChunkExtraIndex(
                index_name="section:鉴权",
                index_kind=IndexKind.SECTION,
                section_path=("鉴权",),
            ),
        ),
    )
    corpus_repository = _RecordingCorpusRepository()
    corpus_repository.saved = RagChunkingResult(
        parent_chunks=(parent,),
        child_chunks=(child,),
        pipeline="test",
        resource_id="resource-doc",
        document_version="3",
    )

    direct_evidence = await RagEvidenceMaterializer(
        corpus_repository=corpus_repository
    ).materialize(
        RagEvidenceMaterializeRequest(
            ranked=(
                RankedCandidate(
                    candidate=RankCandidate(
                        candidate_id="child-1",
                        text="Qdrant payload text",
                    ),
                    rank=1,
                    score=0.82,
                ),
            ),
            retrieved_chunks=(
                ScoredChunk(
                    chunk_id="child-1",
                    text="Qdrant payload text",
                    retrieval_score=0.91,
                    retrieval_rank=1,
                    resource_id="resource-doc",
                    document_version="3",
                    corpus_version="3",
                ),
            ),
            elastic_candidate_chunk_ids=("child-1",),
        )
    )

    assert direct_evidence[0].text == "父块完整上下文，包含鉴权接口和调用限制。"
    assert direct_evidence[0].matched_child_chunks[0].chunk_id == "child-1"
    assert direct_evidence[0].matched_child_chunks[0].text == "子块原文：必须携带 AppBuilder API Key。"
    assert direct_evidence[0].citation_anchor == "p.2 | 鉴权"
    assert direct_evidence[0].elastic_prefiltered


@pytest.mark.anyio
async def test_document_ready_ingestion_rejects_missing_content() -> None:
    service = RagDocumentReadyConsumer(
        ingester=_RecordingIngestionService(),
    )

    with pytest.raises(DocumentReadyMessageError):
        await service.ingest(
            {
                "resourceId": "resource-doc",
                "version": 3,
            }
        )


@pytest.mark.anyio
async def test_document_ready_ingestion_rejects_missing_resource_id() -> None:
    service = RagDocumentReadyConsumer(
        ingester=_RecordingIngestionService(),
    )

    with pytest.raises(DocumentReadyMessageError):
        await service.ingest(
            {
                "version": 3,
                "content": "# 标题",
            }
        )


@pytest.mark.anyio
async def test_qdrant_rrf_order_is_passed_to_rerank_stage_without_fusion() -> None:
    service = RagEvidenceRankingService(
        ranking_engine=_ranking_engine_without_reranker()
    )

    ranking_result = await service.rank(
        RagEvidenceRankingRequest(
            query="AppBuilder API Key 鉴权",
            chunks=(
                _retrieved_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.71,
                    retrieval_rank=1,
                ),
                _retrieved_hit(
                    chunk_id="chunk-b",
                    text="另一个接口说明 Bearer token。",
                    retrieval_score=0.69,
                    retrieval_rank=2,
                ),
                _retrieved_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.64,
                    retrieval_rank=3,
                ),
            ),
            top_k=2,
        )
    )

    assert [item.candidate_id for item in ranking_result.ranked] == ["chunk-a", "chunk-b"]
    assert [item.candidate.prior_rank for item in ranking_result.ranked] == [1, 2]
    assert ranking_result.ranked[0].candidate.metadata == {"retrieval_score": 0.71}
    assert all(not item.signals for item in ranking_result.ranked)


def test_hard_gate_rejects_empty_retrieval() -> None:
    decision = AnswerabilityHardGate().decide(
        RagAnswerabilityInput(
            query="AppBuilder API Key 鉴权",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(),
        )
    )

    assert not decision.should_continue
    assert decision.reason == RagHardGateReason.EMPTY_RETRIEVAL


def test_hard_gate_rejects_when_all_topk_scores_are_extremely_low() -> None:
    decision = AnswerabilityHardGate().decide(
        RagAnswerabilityInput(
            query="AppBuilder API Key 鉴权",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(
                RankedCandidate(
                    candidate=RankCandidate(
                        candidate_id="chunk-low",
                        text="AppBuilder API Key 用于接口鉴权。",
                    ),
                    rank=1,
                    score=0.01,
                ),
            ),
        )
    )

    assert not decision.should_continue
    assert decision.reason == RagHardGateReason.TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE


@pytest.mark.anyio
async def test_soft_gate_returns_warning_and_triggers_graph_enhancement() -> None:
    warning = await AnswerabilitySoftGate(client=_SoftGateClient()).evaluate(
        RagAnswerabilityInput(
            query="AppBuilder API Key 鉴权覆盖哪些接口？",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(
                RankedCandidate(
                    candidate=RankCandidate(
                        candidate_id="chunk-partial",
                        text="AppBuilder API Key 用于部分接口鉴权。",
                    ),
                    rank=1,
                    score=0.42,
                ),
            ),
        )
    )

    assert warning.warnings == (RagAnswerabilityWarningReason.PARTIAL_COVERAGE,)
    assert warning.should_enhance_with_neo4j


@pytest.mark.anyio
async def test_soft_gate_filters_unknown_warning_reason() -> None:
    service = AnswerabilitySoftGate(client=_SoftGateClient(
        content=(
            '{"warnings":["NOT_A_REAL_WARNING","PARTIAL_COVERAGE","PARTIAL_COVERAGE"],'
            '"guidance":"只保留有效 warning。"}'
        )
    ))

    warning = await service.evaluate(
        RagAnswerabilityInput(
            query="这里的 Apple 指哪个公司？",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(
                RankedCandidate(
                    candidate=RankCandidate(
                        candidate_id="chunk-ambiguous",
                        text="Apple 在不同上下文中可能指公司或水果。",
                    ),
                    rank=1,
                    score=0.51,
                ),
            ),
        )
    )

    assert warning.warnings == (RagAnswerabilityWarningReason.PARTIAL_COVERAGE,)


def _retrieved_hit(
    *,
    chunk_id: str,
    text: str,
    retrieval_score: float,
    retrieval_rank: int,
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        text=text,
        retrieval_score=retrieval_score,
        retrieval_rank=retrieval_rank,
    )


class _SoftGateClient:
    def __init__(self, *, content: str | None = None) -> None:
        self._content = content or (
            '{"warnings":["PARTIAL_COVERAGE"],'
            '"guidance":"当前证据只覆盖部分接口，回答时说明范围限制。"}'
        )

    async def aquery(self, *args, **kwargs):
        return _SoftGateResponse(
            content=self._content
        )


class _SoftGateResponse:
    def __init__(self, *, content: str) -> None:
        self.content = content
        self.usage_tokens = 12


class _RecordingIngestionService:
    def __init__(self) -> None:
        self.payload: RagMarkdownIngestionPayload | None = None

    async def ingest_markdown(self, payload: RagMarkdownIngestionPayload) -> RagMarkdownIngestResult:
        self.payload = payload
        return RagMarkdownIngestResult(
            parent_chunks=(),
            child_chunks=(),
            pipeline="test",
            resource_id=payload.resource_id,
            document_version=payload.document_version,
            corpus_version=payload.document_version,
            indexed_child_count=0,
            acl_projection=None,
        )


class _RecordingCorpusRepository:
    def __init__(self) -> None:
        self.saved: RagChunkingResult | None = None

    async def upsert_document(
            self,
            *,
            resource_id: str,
            document_version: str,
            parent_chunks: tuple[RagParentChunk, ...],
            child_chunks: tuple[RagChildChunk, ...],
    ) -> None:
        self.saved = RagChunkingResult(
            parent_chunks=parent_chunks,
            child_chunks=child_chunks,
            pipeline="test",
            resource_id=resource_id,
            document_version=document_version,
        )

    async def load_child_chunks(self, chunk_ids: tuple[str, ...]) -> tuple[RagChildChunk, ...]:
        if self.saved is None:
            return ()

        by_id = {
            chunk.chunk_id: chunk
            for chunk in self.saved.child_chunks
        }
        return tuple(
            chunk
            for chunk_id in chunk_ids
            if (chunk := by_id.get(chunk_id)) is not None
        )

    async def load_parent_chunks(self, chunk_ids: tuple[str, ...]) -> tuple[RagParentChunk, ...]:
        if self.saved is None:
            return ()

        by_id = {
            chunk.chunk_id: chunk
            for chunk in self.saved.parent_chunks
        }
        return tuple(
            chunk
            for chunk_id in chunk_ids
            if (chunk := by_id.get(chunk_id)) is not None
        )


class _PreparedChunkingService:
    def __init__(self, result: RagChunkingResult) -> None:
        self.result = result

    def chunk_payload(self, payload: RagMarkdownIngestionPayload) -> RagChunkingResult:
        return self.result


class _RecordingContextIndexingService:
    async def build(self, payload: ContextIndexingInput) -> ContextIndexingResult:
        return ContextIndexingResult(
            child_chunk=payload.child_chunk.with_indexing_context(
                indexing_context="该片段说明 API 鉴权请求头要求。",
                indexing_text=f"上下文补充: 该片段说明 API 鉴权请求头要求。\n正文: {payload.child_chunk.text}",
            )
        )


class _RecordingEmbeddingClient:
    async def aembed(self, input):
        values = [input] if isinstance(input, str) else list(input)
        return _EmbeddingResponse(
            embeddings=[
                [0.1, 0.2]
                for _ in values
            ]
        )


class _EmbeddingResponse:
    def __init__(self, *, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings


class _RecordingAclRepository:
    def __init__(self, projection: RagResourceAclProjection | None) -> None:
        self.projection = projection

    async def upsert_projection(self, projection: RagResourceAclProjection) -> None:
        self.projection = projection

    async def get_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        return self.projection

    async def load_resource_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        return self.projection


class _RecordingIndexRepository:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, object]] = []

    async def upsert_child_chunks(self, **kwargs) -> None:
        self.upsert_calls.append(kwargs)

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        return None


class _RecordingRetrievalRepository:
    def __init__(self, *, chunks: tuple[ScoredChunk, ...] = ()) -> None:
        self.chunks = chunks
        self.retrieve_calls = []

    async def retrieve(self, request):
        self.retrieve_calls.append(request)
        return self.chunks


class _RecordingElasticRepository:
    def __init__(self, *, candidate_chunk_ids: tuple[str, ...] | None) -> None:
        self.candidate_chunk_ids = candidate_chunk_ids
        self.strict_prefilter_calls = []

    async def strict_prefilter(self, request):
        self.strict_prefilter_calls.append(request)
        return self.candidate_chunk_ids or ()


class _RecordingRankingService:
    async def rank(self, request):
        ranked = tuple(
            RankedCandidate(
                candidate=RankCandidate(
                    candidate_id=chunk.chunk_id,
                    text=chunk.text,
                    prior_rank=chunk.retrieval_rank,
                ),
                rank=index,
                score=chunk.retrieval_score or 0.0,
            )
            for index, chunk in enumerate(request.chunks, start=1)
        )
        return _RankingResult(ranked=ranked, total_candidates=len(request.chunks))


class _RankingResult:
    def __init__(self, *, ranked, total_candidates: int) -> None:
        self.ranked = ranked
        self.total_candidates = total_candidates


class _RecordingSoftGate:
    def __init__(self) -> None:
        self.calls = []

    async def evaluate(self, answerability_input):
        self.calls.append(answerability_input)
        return None
