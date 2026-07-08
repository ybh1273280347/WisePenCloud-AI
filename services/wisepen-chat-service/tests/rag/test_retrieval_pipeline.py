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
    RagAnswerabilityWarning,
    RagAnswerabilityWarningReason,
    RagHardGateReason,
)
from chat.application.rag.cache.evidence_materialization import (  # noqa: E402
    RagEvidenceMaterializationCacheScope,
    RagMaterializedEvidenceView,
)
from chat.application.rag.cache.graph_enhancement import (  # noqa: E402
    RagGraphEnhancementCacheKey,
)
from chat.application.rag.cache.ingestion_deterministic import (  # noqa: E402
    RagChunkingCacheKey,
    RagContextIndexingCacheKey,
    RagEmbeddingCacheKey,
)
from chat.application.rag.graph import (  # noqa: E402
    RagGraphEnhancementRequest,
    RagGraphEnhancementResult,
    RagGraphEvidence,
)
from chat.application.rag.retrieval.pipeline.ranking import (  # noqa: E402
    RagEvidenceRankingRequest,
    RagEvidenceRankingService,
)
from chat.application.rag.context_builder import (  # noqa: E402
    RagContextBuilder,
    RagEvidenceMaterializeRequest,
    RagEvidenceMaterializer,
)
from chat.application.rag.retrieval.models import (  # noqa: E402
    RagPermissionScope,
    RagRankedChunk,
    RagRetrievalChannel,
    RagRetrievalProfile,
    RagRetrievalSignal,
    ScoredChunk,
)
from chat.application.rag.retrieval.pipeline.graph_enhancement import (
    RagGraphEnhancement,
)  # noqa: E402
from chat.application.rag.retrieval.retrieval_pipeline import (  # noqa: E402
    RagRetrievalPipeline,
    RagRetrievalPipelineRequest,
)
from chat.application.rag.knowledge_search import (  # noqa: E402
    RagKnowledgeSearcher,
    RagKnowledgeSearchRequest,
)
from chat.application.rag.kafka_consumers.document_ready_consumer import (  # noqa: E402
    DocumentReadyMessageError,
    RagDocumentReadyConsumer,
)
from chat.application.rag.acl import RagResourceAclProjection  # noqa: E402
from chat.application.rag.ingestion.chunking import RagChunkingService  # noqa: E402
from chat.application.rag.ingestion.context_indexing import (  # noqa: E402
    ContextIndexingError,
    ContextIndexingInput,
    ContextIndexingResult,
)
from chat.application.rag.ingestion.models import (  # noqa: E402
    RagChildChunk,
    RagChunkLocator,
    RagChunkingResult,
    RagMarkdownIngestionPayload,
    RagParentChunk,
)
from chat.application.rag.ingestion.ingester import (  # noqa: E402
    RagIngestionRetryableError,
    RagMarkdownIngester,
    RagMarkdownIngestResult,
)
from chat.application.utils.chunking_engine.models import LocatorKind  # noqa: E402
from chat.application.utils.ranking_engine.models import (  # noqa: E402
    RankCandidate,
    RankedCandidate,
)
from chat.application.utils.ranking_engine.engine import RankingEngine  # noqa: E402
from chat.application.utils.ranking_engine.fusion import WeightedRrfFusion  # noqa: E402
from chat.application.utils.ranking_engine.pipeline import RankingPipeline  # noqa: E402


def _ranking_engine_with_external_rrf() -> RankingEngine:
    return RankingEngine(
        pipeline=RankingPipeline(
            name="test.rag.knowledge_search",
            fusion=WeightedRrfFusion(),
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


def test_chunking_service_persists_locators_for_evidence_location() -> None:
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

    all_locators = tuple(
        locator
        for chunk in (*result.parent_chunks, *result.child_chunks)
        for locator in chunk.locators
    )
    assert all_locators
    assert {locator.locator_name for locator in all_locators} >= {"page:1", "page:2"}

    page_one = next(
        locator for locator in all_locators if locator.locator_name == "page:1"
    )
    page_two = next(
        locator for locator in all_locators if locator.locator_name == "page:2"
    )
    assert page_one.locator_kind == LocatorKind.PAGE
    assert page_two.locator_kind == LocatorKind.PAGE
    assert page_one.start_offset == 0
    assert page_one.end_offset is not None
    assert page_two.start_offset == page_one.end_offset

    page_one_chunks = [
        chunk
        for chunk in result.child_chunks
        if any(locator.locator_name == "page:1" for locator in chunk.locators)
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
async def test_rag_ingestion_locators_corpus_qdrant_and_elastic_with_acl_projection() -> (
    None
):
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
    graph_repository = _RecordingGraphRepository()
    graph_builder = _RecordingKnowledgeGraphBuilder()
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
        graph_repository=graph_repository,
        knowledge_graph_builder=graph_builder,
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
    assert (
        corpus_repository.saved.child_chunks[0].indexing_context
        == "该片段说明 API 鉴权请求头要求。"
    )
    assert qdrant_repository.upsert_calls[0]["dense_vectors"] == {"child-1": [0.1, 0.2]}
    assert "sparse_vectors" not in qdrant_repository.upsert_calls[0]
    assert qdrant_repository.upsert_calls[0]["acl_projection"] == acl_projection
    assert elastic_repository.upsert_calls[0]["child_chunks"][0].indexing_text
    assert elastic_repository.upsert_calls[0]["acl_projection"] == acl_projection
    assert graph_repository.delete_calls == [
        {"resource_id": "resource-doc", "document_version": "3"}
    ]
    assert graph_builder.upsert_calls[0]["dense_vectors"] == {"child-1": [0.1, 0.2]}
    assert graph_repository.acl_updates == [acl_projection]


@pytest.mark.anyio
async def test_rag_ingestion_retries_context_indexing_failure_without_writing_locators() -> (
    None
):
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
        context_indexing_service=_FailingContextIndexingService(),
        embedding_client=_RecordingEmbeddingClient(),
        corpus_repository=corpus_repository,
        acl_repository=_RecordingAclRepository(None),
        qdrant_repository=qdrant_repository,
        elastic_repository=elastic_repository,
    )

    with pytest.raises(RagIngestionRetryableError):
        await service.ingest_markdown(
            RagMarkdownIngestionPayload(
                resource_id="resource-doc",
                document_version="3",
                markdown="# 鉴权\n\n请求必须携带 Authorization header。",
            )
        )

    assert corpus_repository.saved is None
    assert qdrant_repository.upsert_calls == []
    assert elastic_repository.upsert_calls == []


@pytest.mark.anyio
async def test_rag_ingestion_uses_deterministic_cache_for_repeated_payload() -> None:
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
    chunking_service = _PreparedChunkingService(
        RagChunkingResult(
            parent_chunks=(parent,),
            child_chunks=(child,),
            pipeline="parent_child_markdown",
            resource_id="resource-doc",
            document_version="3",
        )
    )
    context_indexing_service = _RecordingContextIndexingService()
    embedding_client = _RecordingEmbeddingClient()
    service = RagMarkdownIngester(
        chunking_service=chunking_service,
        context_indexing_service=context_indexing_service,
        embedding_client=embedding_client,
        corpus_repository=_RecordingCorpusRepository(),
        acl_repository=_RecordingAclRepository(None),
        qdrant_repository=_RecordingIndexRepository(),
        elastic_repository=_RecordingIndexRepository(),
        ingestion_cache=_RecordingIngestionCache(),
        summary_model="summary-model",
        embedding_model="embedding-model",
        embedding_dimensions=2,
    )
    payload = RagMarkdownIngestionPayload(
        resource_id="resource-doc",
        document_version="3",
        markdown="# 鉴权\n\n请求必须携带 Authorization header。",
    )

    await service.ingest_markdown(payload)
    await service.ingest_markdown(payload)

    assert chunking_service.calls == 1
    assert context_indexing_service.calls == 1
    assert embedding_client.calls == 1


@pytest.mark.anyio
async def test_knowledge_search_runs_elastic_scope_qdrant_bm25_ranking_and_gates() -> (
    None
):
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
    graph_repository = _RecordingGraphRepository(
        result=RagGraphEnhancementResult(
            graph_evidence=(
                RagGraphEvidence(
                    chunk_id="child-2",
                    document_version="3",
                    evidence_text="Graph 补充证据说明 API Key 的申请入口。",
                    page_label="1",
                    section_path=("鉴权",),
                    path=("child-1", "child-2"),
                ),
            )
        )
    )
    ranking_service = _RecordingRankingService()
    service = RagKnowledgeSearcher(
        retrieval_pipeline=RagRetrievalPipeline(
            embedding_client=_RecordingEmbeddingClient(),
            elastic_filter=_RecordingElasticFilter(candidate_chunk_ids=("child-1",)),
            qdrant_retriever=qdrant_repository,
            ranking_service=ranking_service,
            hard_gate=AnswerabilityHardGate(),
            soft_gate=soft_gate,
            evidence_materializer=RagEvidenceMaterializer(
                corpus_repository=_RecordingCorpusRepository(),
                cache=_RecordingEvidenceCache(),
            ),
            graph_enhancement=RagGraphEnhancement(repository=graph_repository),
        ),
        context_builder=RagContextBuilder(),
    )

    result = await service.search(
        RagKnowledgeSearchRequest(
            query="AppBuilder API Key",
            resource_id="resource-doc",
            retrieval_profile=RagRetrievalProfile.LEXICAL,
            keywords=("API Key",),
            permission_scope=RagPermissionScope(
                user_id="user-1",
                group_role_map={"group-1": "MEMBER"},
            ),
            session_id="session-1",
        )
    )

    retrieval_request = qdrant_repository.retrieve_calls[0]
    assert retrieval_request.candidate_chunk_ids == ("child-1",)
    assert retrieval_request.query_text == "AppBuilder API Key"
    assert ranking_service.calls[0].retrieval_profile == RagRetrievalProfile.LEXICAL
    assert retrieval_request.permission_scope is not None
    assert result.should_continue
    assert result.direct_evidence[0].citation_id == "E1"
    assert result.direct_evidence[0].page_label == "1"
    assert result.direct_evidence[0].section_path == ("鉴权",)
    assert result.context is not None
    assert "AppBuilder API Key" in result.context.context_text
    assert "Graph 补充证据" in result.context.context_text
    assert "parent_chunk_id" not in result.context.context_text
    assert "score=" not in result.context.context_text
    assert graph_repository.expand_calls
    assert soft_gate.calls


@pytest.mark.anyio
async def test_knowledge_search_stops_when_elastic_strict_prefilter_is_empty() -> None:
    qdrant_repository = _RecordingRetrievalRepository()
    service = RagKnowledgeSearcher(
        retrieval_pipeline=RagRetrievalPipeline(
            embedding_client=_RecordingEmbeddingClient(),
            elastic_filter=_RecordingElasticFilter(candidate_chunk_ids=()),
            qdrant_retriever=qdrant_repository,
            ranking_service=_RecordingRankingService(),
            hard_gate=AnswerabilityHardGate(),
            soft_gate=_RecordingSoftGate(),
            evidence_materializer=RagEvidenceMaterializer(
                corpus_repository=_RecordingCorpusRepository()
            ),
        ),
        context_builder=RagContextBuilder(),
    )

    result = await service.search(
        RagKnowledgeSearchRequest(
            query="不存在的锚点",
            resource_id="resource-doc",
            retrieval_profile=RagRetrievalProfile.LEXICAL,
            keywords=("不存在的锚点",),
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
        locators=(
            RagChunkLocator(
                locator_name="page:2",
                locator_kind=LocatorKind.PAGE,
                page_label="2",
            ),
            RagChunkLocator(
                locator_name="section:鉴权",
                locator_kind=LocatorKind.SECTION,
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
            candidates=(
                _ranked_chunk(
                    chunk_id="child-1",
                    text="Qdrant payload text",
                    rank=1,
                    score=0.82,
                    retrieval_score=0.91,
                    retrieval_rank=1,
                    resource_id="resource-doc",
                    document_version="3",
                    corpus_version="3",
                ),
            ),
        )
    )

    assert direct_evidence[0].text == "父块完整上下文，包含鉴权接口和调用限制。"
    assert direct_evidence[0].matched_child_ids == ("child-1",)
    assert direct_evidence[0].page_label == "2"
    assert direct_evidence[0].section_path == ("鉴权",)


@pytest.mark.anyio
async def test_evidence_materializer_uses_cache_without_storing_rank_score() -> None:
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
    )
    corpus_repository = _RecordingCorpusRepository()
    corpus_repository.saved = RagChunkingResult(
        parent_chunks=(parent,),
        child_chunks=(child,),
        pipeline="test",
        resource_id="resource-doc",
        document_version="3",
    )
    scope = RagEvidenceMaterializationCacheScope(
        user_id="user-1",
        session_id="session-1",
        resource_id="resource-doc",
        permission_scope_key="group-1:MEMBER",
    )
    materializer = RagEvidenceMaterializer(
        corpus_repository=corpus_repository,
        cache=_RecordingEvidenceCache(),
    )

    first = await materializer.materialize(
        RagEvidenceMaterializeRequest(
            candidates=(
                _ranked_chunk(
                    chunk_id="child-1",
                    text="Qdrant payload text",
                    rank=1,
                    score=0.91,
                    retrieval_score=0.91,
                    retrieval_rank=1,
                    resource_id="resource-doc",
                    document_version="3",
                    corpus_version="3",
                    parent_chunk_id="parent-1",
                ),
            ),
            cache_scope=scope,
        )
    )
    second = await materializer.materialize(
        RagEvidenceMaterializeRequest(
            candidates=(
                _ranked_chunk(
                    chunk_id="child-1",
                    text="Qdrant payload text",
                    rank=2,
                    score=0.81,
                    retrieval_score=0.91,
                    retrieval_rank=1,
                    resource_id="resource-doc",
                    document_version="3",
                    corpus_version="3",
                    parent_chunk_id="parent-1",
                ),
            ),
            cache_scope=scope,
        )
    )

    assert first[0].citation_id == "E1"
    assert second[0].citation_id == "E2"
    assert second[0].matched_child_ids == ("child-1",)
    assert corpus_repository.load_child_calls == [("child-1",), ()]


@pytest.mark.anyio
async def test_graph_enhancement_uses_cache_for_same_warning_scope() -> None:
    repository = _RecordingGraphRepository(
        result=RagGraphEnhancementResult(
            graph_evidence=(
                RagGraphEvidence(
                    chunk_id="child-2",
                    document_version="3",
                    evidence_text="Graph 补充证据。",
                    page_label="1",
                ),
            )
        )
    )
    service = RagGraphEnhancement(
        repository=repository,
        cache=_RecordingGraphCache(),
        graph_version="graph-v1",
        ontology_schema_version="ontology-v1",
    )
    request = RagGraphEnhancementRequest(
        query="API Key 覆盖哪些接口？",
        resource_id="resource-doc",
        direct_evidence=(_direct_evidence_for_graph(),),
        answerability_warning=RagAnswerabilityWarning(
            warnings=(RagAnswerabilityWarningReason.PARTIAL_COVERAGE,),
            guidance="需要补充图证据。",
        ),
        permission_scope=RagPermissionScope(
            user_id="user-1",
            group_role_map={"group-1": "MEMBER"},
        ),
    )

    first = await service.enhance(request)
    second = await service.enhance(request)

    assert first.graph_evidence[0].chunk_id == "child-2"
    assert second.graph_evidence[0].chunk_id == "child-2"
    assert len(repository.expand_calls) == 1


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
async def test_document_ready_ingestion_rejects_non_string_resource_id() -> None:
    service = RagDocumentReadyConsumer(
        ingester=_RecordingIngestionService(),
    )

    with pytest.raises(DocumentReadyMessageError):
        await service.ingest(
            {
                "resourceId": 123,
                "version": 3,
                "content": "# 标题",
            }
        )


@pytest.mark.anyio
async def test_document_ready_ingestion_rethrows_retryable_ingestion_failure() -> None:
    service = RagDocumentReadyConsumer(
        ingester=_FailingIngestionService(),
    )

    with pytest.raises(RagIngestionRetryableError):
        await service.ingest(
            {
                "resourceId": "resource-doc",
                "version": 3,
                "content": "# 标题",
            }
        )


@pytest.mark.anyio
async def test_rag_ranking_converts_qdrant_channel_ranks_to_external_rrf_signals() -> (
    None
):
    service = RagEvidenceRankingService(
        ranking_engine=_ranking_engine_with_external_rrf(),
        lexical_dense_rrf_weight=1.0,
        lexical_sparse_rrf_weight=3.0,
    )

    ranking_result = await service.rank(
        RagEvidenceRankingRequest(
            query="AppBuilder API Key 鉴权",
            chunks=(
                _retrieved_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.40,
                    retrieval_rank=1,
                    retrieval_signals=(
                        RagRetrievalSignal(
                            channel=RagRetrievalChannel.DENSE,
                            rank=1,
                            score=0.40,
                        ),
                    ),
                ),
                _retrieved_hit(
                    chunk_id="chunk-b",
                    text="另一个接口说明 Bearer token。",
                    retrieval_score=0.90,
                    retrieval_rank=2,
                    retrieval_signals=(
                        RagRetrievalSignal(
                            channel=RagRetrievalChannel.SPARSE,
                            rank=1,
                            score=0.90,
                        ),
                    ),
                ),
                _retrieved_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.99,
                    retrieval_rank=3,
                    retrieval_signals=(
                        RagRetrievalSignal(
                            channel=RagRetrievalChannel.SPARSE,
                            rank=1,
                            score=0.99,
                        ),
                    ),
                ),
            ),
            retrieval_profile=RagRetrievalProfile.LEXICAL,
            top_k=2,
        )
    )

    assert [item.candidate_id for item in ranking_result.ranked] == [
        "chunk-b",
        "chunk-a",
    ]
    assert [item.candidate.prior_rank for item in ranking_result.ranked] == [2, 1]
    assert [item.signals[0].value for item in ranking_result.ranked] == [0.90, 0.40]
    assert [item.signals[0].rank for item in ranking_result.ranked] == [1, 1]
    assert [item.score for item in ranking_result.ranked] == pytest.approx(
        [
            3.0 / 61.0,
            1.0 / 61.0,
        ]
    )


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


def test_hard_gate_accepts_only_candidates_above_absolute_threshold() -> None:
    hard_gate = AnswerabilityHardGate()

    assert hard_gate.accepts(0.3)
    assert not hard_gate.accepts(0.29)


@pytest.mark.anyio
async def test_retrieval_pipeline_filters_low_score_candidates_before_materialization() -> (
    None
):
    soft_gate = _RecordingSoftGate()
    pipeline = RagRetrievalPipeline(
        embedding_client=_RecordingEmbeddingClient(),
        elastic_filter=_RecordingElasticFilter(candidate_chunk_ids=None),
        qdrant_retriever=_RecordingRetrievalRepository(
            chunks=(
                ScoredChunk(
                    chunk_id="child-strong",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.72,
                    retrieval_rank=1,
                    resource_id="resource-doc",
                    document_version="3",
                    corpus_version="ctx-v1",
                    parent_chunk_id="parent-1",
                ),
                ScoredChunk(
                    chunk_id="child-weak",
                    text="无关的低质量候选。",
                    retrieval_score=0.12,
                    retrieval_rank=2,
                    resource_id="resource-doc",
                    document_version="3",
                    corpus_version="ctx-v1",
                    parent_chunk_id="parent-2",
                ),
            )
        ),
        ranking_service=_RecordingRankingService(),
        hard_gate=AnswerabilityHardGate(),
        soft_gate=soft_gate,
        evidence_materializer=RagEvidenceMaterializer(
            corpus_repository=_RecordingCorpusRepository(),
            cache=_RecordingEvidenceCache(),
        ),
    )

    result = await pipeline.retrieve(
        RagRetrievalPipelineRequest(
            query="AppBuilder API Key 鉴权",
            resource_id="resource-doc",
            session_id="session-1",
            permission_scope=RagPermissionScope(
                user_id="user-1",
                group_role_map={},
            ),
        )
    )

    assert result.hard_gate is not None
    assert result.hard_gate.should_continue
    assert [item.chunk.chunk_id for item in result.candidates] == ["child-strong"]
    assert [item.matched_child_ids for item in result.direct_evidence] == [
        ("child-strong",)
    ]
    assert [item.candidate_id for item in soft_gate.calls[0].ranked] == ["child-strong"]


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
    service = AnswerabilitySoftGate(
        client=_SoftGateClient(
            content=(
                '{"warnings":["NOT_A_REAL_WARNING","PARTIAL_COVERAGE","PARTIAL_COVERAGE"],'
                '"guidance":"只保留有效 warning。"}'
            )
        )
    )

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
    retrieval_signals: tuple[RagRetrievalSignal, ...] = (),
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        text=text,
        retrieval_score=retrieval_score,
        retrieval_rank=retrieval_rank,
        retrieval_signals=retrieval_signals,
    )


def _ranked_chunk(
    *,
    chunk_id: str,
    text: str,
    rank: int,
    score: float,
    retrieval_score: float,
    retrieval_rank: int,
    resource_id: str = "",
    document_version: str = "",
    corpus_version: str = "",
    parent_chunk_id: str = "",
) -> RagRankedChunk:
    chunk = ScoredChunk(
        chunk_id=chunk_id,
        text=text,
        retrieval_score=retrieval_score,
        retrieval_rank=retrieval_rank,
        resource_id=resource_id,
        document_version=document_version,
        corpus_version=corpus_version,
        parent_chunk_id=parent_chunk_id,
    )
    return RagRankedChunk(
        ranking=RankedCandidate(
            candidate=RankCandidate(
                candidate_id=chunk_id,
                text=text,
                prior_rank=retrieval_rank,
            ),
            rank=rank,
            score=score,
        ),
        chunk=chunk,
    )


def _direct_evidence_for_graph():
    from chat.application.rag.context_builder import RagDirectEvidence

    return RagDirectEvidence(
        citation_id="E1",
        document_version="3",
        text="父块证据。",
        page_label="1",
        matched_child_ids=("child-1",),
    )


class _SoftGateClient:
    def __init__(self, *, content: str | None = None) -> None:
        self._content = content or (
            '{"warnings":["PARTIAL_COVERAGE"],'
            '"guidance":"当前证据只覆盖部分接口，回答时说明范围限制。"}'
        )

    async def aquery(self, *args, **kwargs):
        return _SoftGateResponse(content=self._content)


class _SoftGateResponse:
    def __init__(self, *, content: str) -> None:
        self.content = content
        self.usage_tokens = 12


class _RecordingIngestionService:
    def __init__(self) -> None:
        self.payload: RagMarkdownIngestionPayload | None = None

    async def ingest_markdown(
        self, payload: RagMarkdownIngestionPayload
    ) -> RagMarkdownIngestResult:
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


class _FailingIngestionService:
    async def ingest_markdown(
        self, payload: RagMarkdownIngestionPayload
    ) -> RagMarkdownIngestResult:
        raise RagIngestionRetryableError("retry ingestion")


class _RecordingCorpusRepository:
    def __init__(self) -> None:
        self.saved: RagChunkingResult | None = None
        self.load_child_calls: list[tuple[str, ...]] = []
        self.load_parent_calls: list[tuple[str, ...]] = []

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

    async def load_child_chunks(
        self, chunk_ids: tuple[str, ...]
    ) -> tuple[RagChildChunk, ...]:
        self.load_child_calls.append(chunk_ids)
        if self.saved is None:
            return ()

        by_id = {chunk.chunk_id: chunk for chunk in self.saved.child_chunks}
        return tuple(
            chunk
            for chunk_id in chunk_ids
            if (chunk := by_id.get(chunk_id)) is not None
        )

    async def load_parent_chunks(
        self, chunk_ids: tuple[str, ...]
    ) -> tuple[RagParentChunk, ...]:
        self.load_parent_calls.append(chunk_ids)
        if self.saved is None:
            return ()

        by_id = {chunk.chunk_id: chunk for chunk in self.saved.parent_chunks}
        return tuple(
            chunk
            for chunk_id in chunk_ids
            if (chunk := by_id.get(chunk_id)) is not None
        )


class _PreparedChunkingService:
    def __init__(self, result: RagChunkingResult) -> None:
        self.result = result
        self.calls = 0

    def chunk_payload(self, payload: RagMarkdownIngestionPayload) -> RagChunkingResult:
        self.calls += 1
        return self.result


class _RecordingContextIndexingService:
    def __init__(self) -> None:
        self.calls = 0

    async def build(self, payload: ContextIndexingInput) -> ContextIndexingResult:
        self.calls += 1
        return ContextIndexingResult(
            child_chunk=payload.child_chunk.with_indexing_context(
                indexing_context="该片段说明 API 鉴权请求头要求。",
                indexing_text=f"上下文补充: 该片段说明 API 鉴权请求头要求。\n正文: {payload.child_chunk.text}",
            )
        )


class _FailingContextIndexingService:
    async def build(self, payload: ContextIndexingInput) -> ContextIndexingResult:
        raise ContextIndexingError("context indexing failed")


class _RecordingEmbeddingClient:
    def __init__(self) -> None:
        self.calls = 0

    async def aembed(self, input):
        self.calls += 1
        values = [input] if isinstance(input, str) else list(input)
        return _EmbeddingResponse(embeddings=[[0.1, 0.2] for _ in values])


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

    async def load_resource_projection(
        self, resource_id: str
    ) -> RagResourceAclProjection | None:
        return self.projection


class _RecordingIndexRepository:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, object]] = []

    async def upsert_child_chunks(self, **kwargs) -> None:
        self.upsert_calls.append(kwargs)

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        return None


class _RecordingGraphRepository:
    def __init__(self, *, result: RagGraphEnhancementResult | None = None) -> None:
        self.result = result or RagGraphEnhancementResult()
        self.delete_calls: list[dict[str, object]] = []
        self.acl_updates: list[RagResourceAclProjection] = []
        self.expand_calls = []

    async def delete_document_projection(self, **kwargs) -> None:
        self.delete_calls.append(kwargs)

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        self.acl_updates.append(projection)

    async def expand_for_warnings(self, request):
        self.expand_calls.append(request)
        return self.result


class _RecordingKnowledgeGraphBuilder:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, object]] = []

    async def upsert_document_graph(self, **kwargs) -> None:
        self.upsert_calls.append(kwargs)


class _RecordingEvidenceCache:
    def __init__(self) -> None:
        self.values: dict[str, RagMaterializedEvidenceView] = {}

    async def get_many(
        self,
        *,
        scope: RagEvidenceMaterializationCacheScope,
        child_chunk_ids: tuple[str, ...],
    ) -> dict[str, RagMaterializedEvidenceView]:
        return {
            child_id: view
            for child_id in child_chunk_ids
            if (view := self.values.get(child_id)) is not None
        }

    async def set_many(
        self,
        *,
        scope: RagEvidenceMaterializationCacheScope,
        views_by_child_id: dict[str, RagMaterializedEvidenceView],
    ) -> None:
        self.values.update(views_by_child_id)


class _RecordingIngestionCache:
    def __init__(self) -> None:
        self.chunking: dict[RagChunkingCacheKey, RagChunkingResult] = {}
        self.context_children: dict[RagContextIndexingCacheKey, RagChildChunk] = {}
        self.embedding_vectors: dict[RagEmbeddingCacheKey, list[float]] = {}

    async def get_chunking_result(
        self, key: RagChunkingCacheKey
    ) -> RagChunkingResult | None:
        return self.chunking.get(key)

    async def set_chunking_result(
        self,
        key: RagChunkingCacheKey,
        result: RagChunkingResult,
    ) -> None:
        self.chunking[key] = result

    async def get_context_indexed_child(
        self,
        key: RagContextIndexingCacheKey,
    ) -> RagChildChunk | None:
        return self.context_children.get(key)

    async def set_context_indexed_child(
        self,
        key: RagContextIndexingCacheKey,
        child: RagChildChunk,
    ) -> None:
        self.context_children[key] = child

    async def get_embedding_vectors(
        self,
        keys: dict[str, RagEmbeddingCacheKey],
    ) -> dict[str, list[float]]:
        return {
            chunk_id: vector
            for chunk_id, key in keys.items()
            if (vector := self.embedding_vectors.get(key)) is not None
        }

    async def set_embedding_vectors(
        self,
        vectors: dict[str, tuple[RagEmbeddingCacheKey, list[float]]],
    ) -> None:
        for key, vector in vectors.values():
            self.embedding_vectors[key] = vector


class _RecordingGraphCache:
    def __init__(self) -> None:
        self.values: dict[RagGraphEnhancementCacheKey, RagGraphEnhancementResult] = {}

    async def get_graph_enhancement(
        self,
        key: RagGraphEnhancementCacheKey,
    ) -> RagGraphEnhancementResult | None:
        return self.values.get(key)

    async def set_graph_enhancement(
        self,
        key: RagGraphEnhancementCacheKey,
        result: RagGraphEnhancementResult,
    ) -> None:
        self.values[key] = result


class _RecordingRetrievalRepository:
    def __init__(self, *, chunks: tuple[ScoredChunk, ...] = ()) -> None:
        self.chunks = chunks
        self.retrieve_calls = []

    async def retrieve(self, request):
        self.retrieve_calls.append(request)
        return self.chunks


class _RecordingElasticFilter:
    def __init__(self, *, candidate_chunk_ids: tuple[str, ...] | None) -> None:
        self.candidate_chunk_ids = candidate_chunk_ids
        self.filter_candidate_chunk_ids_calls = []

    async def filter_candidate_chunk_ids(self, request):
        self.filter_candidate_chunk_ids_calls.append(request)
        return self.candidate_chunk_ids or ()


class _RecordingRankingService:
    def __init__(self) -> None:
        self.calls = []

    async def rank(self, request):
        self.calls.append(request)
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
        return RagAnswerabilityWarning(
            warnings=(RagAnswerabilityWarningReason.PARTIAL_COVERAGE,),
            guidance="需要补充图证据。",
        )
