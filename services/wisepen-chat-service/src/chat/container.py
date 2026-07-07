# src/chat/container.py

from typing import List

import hishel.httpx as hishel_httpx
import httpx
from dependency_injector import containers, providers
from elasticsearch import AsyncElasticsearch
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models
from v2.nacos import NacosNamingService

from chat.application.agents import (
    DefaultAgentResolver,
)
from chat.application.chat_turn_coordinator import ChatTurnCoordinator
from chat.application.llm_provider_resolver import LLMProviderResolver
from chat.application.rag.acl import RagAclProjectionProjector, RagAclProjectionUpdater
from chat.application.rag.answerability import AnswerabilityHardGate, AnswerabilitySoftGate
from chat.application.rag.context_builder import RagContextBuilder, RagEvidenceMaterializer
from chat.application.rag.ingestion import (
    ContextIndexingService,
    RagMarkdownIngester,
    RagChunkingService,
)
from chat.application.rag.kafka_consumers.acl_recalculate_consumer import RagAclRecalculateConsumer
from chat.application.rag.kafka_consumers.document_ready_consumer import RagDocumentReadyConsumer
from chat.application.rag.ranking import RagEvidenceRankingService
from chat.application.rag.retrieval import (
    RagElasticRetriever,
    RagHybridRetriever,
    RagPermissionFilterBuilder,
    RagQdrantRetriever,
)
from chat.application.rag.knowledge_search import RagKnowledgeSearcher
from chat.application.token_counter import TokenCounter
from chat.application.tools.common.tool_content_store.store import (
    DEFAULT_TOOL_CONTENT_TTL_SECONDS,
    ToolContentStore,
)
from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.tool_run_file_store.gc import (
    ToolRunFileStoreGcScheduler,
)
from chat.application.tools.common.web_content_cache.gc import WebContentCacheGcScheduler
from chat.application.tools.core import ToolRegistry
from chat.application.tools.core.execution.dispatcher import ToolDispatcher
from chat.application.tools.document_tools import DocumentParseTool, ImageOcrTool
from chat.application.tools.document_tools.document_parse import DocumentParseService
from chat.application.tools.document_tools.ocr import (
    PaddleCloudClient,
    PaddleCloudConfig,
)
from chat.application.tools.math_tools import (
    CalculusSolveTool,
    EquationSolveTool,
    ExpressionSolveTool,
    LinearAlgebraSolveTool,
    StatsSolveTool,
)
from chat.application.tools.session_tools import (
    GetHistoricalChatMessagesTool,
    ToolContentReadTool,
    ToolContentSequentialReadTool,
)
from chat.application.tools.skill_tools import LoadSkillAssetTool, LoadSkillTool
from chat.application.tools.skill_tools.utils.skill_matcher import DefaultSkillMatcher
from chat.application.tools.tool_output_cache import ToolOutputCache
from chat.application.tools.tool_output_renderer import ToolOutputRenderer
from chat.application.tools.tool_settings import tool_settings
from chat.application.tools.web_tools import (
    AcademicSearchTool,
    WebCrawlTool,
    WebFetchTool,
    WebSearchTool,
)
from chat.application.tools.web_tools.search_services.factories.custom_source_factory import (
    WebSearchCustomSourceFactory,
)
from chat.application.tools.web_tools.search_services.factories.integration_searcher_factory import (
    IntegrationSearcherFactory,
)
from chat.application.tools.web_tools.search_services.factories.platform_source_factory import (
    WebSearchPlatformSourceFactory,
)
from chat.application.tools.web_tools.search_services.core.runtime_context import (
    WebSearchRuntimeContextResolver,
)
from chat.application.tools.web_tools.search_services.searchers import (
    DdgSearcher,
    FourGetSearcher,
    PlatformDefaultSearcher,
    ProviderSearcher,
    SearchProviderConfig,
)
from chat.application.tools.web_tools.search_services.hydrators.academic import PaperHydrator
from chat.application.tools.web_tools.search_services.academic_search import AcademicSearchService
from chat.application.tools.web_tools.search_services.web_search import WebSearchService
from chat.application.tools.web_tools.fetch_services import (
    FetchCoordinator,
    WebCrawler,
)
from chat.application.tools.web_tools.fetch_services.cleaners.trafilatura_cleaner import (
    TrafilaturaCleaner,
)
from chat.application.tools.web_tools.fetch_services.fetchers import (
    HttpxFetcher,
    ScraplingFetcher,
)
from chat.application.utils.llm_clients.embedding import build_embedding_client
from chat.core.config.app_settings import settings
from chat.core.config.bootstrap_settings import bootstrap_settings
from chat.core.config.nacos import nacos_client_manager
from chat.core.persistence.mongo.message_repository import MongoMessageRepository
from chat.core.persistence.mongo.model_repository import MongoModelRepository
from chat.core.persistence.mongo.provider_repository import MongoProviderRepository
from chat.core.persistence.mongo.rag_acl_projection_repository import (
    MongoRagAclProjectionRepository,
)
from chat.core.persistence.mongo.rag_corpus_repository import MongoRagCorpusRepository
from chat.core.persistence.mongo.session_repository import MongoSessionRepository
from chat.core.persistence.mongo.web_content_cache_value_repository import (
    MongoWebContentCacheValueRepository,
)
from chat.core.persistence.mongo.web_search_credential_repository import (
    MongoWebSearchCredentialRepository,
)
from chat.core.persistence.redis.hot_context import RedisHotContext
from chat.core.persistence.redis.tool_content_repository import RedisToolContentRepository
from chat.core.persistence.redis.tool_run_file_repository import RedisToolRunFileRepository
from chat.core.persistence.redis.web_content_cache_entry_repository import (
    RedisWebContentCacheEntryRepository,
)
from chat.core.persistence.redis.web_search_candidate_repository import (
    RedisWebSearchCandidateRepository,
)
from chat.core.persistence.elasticsearch import RagElasticRepository
from chat.core.persistence.qdrant import RagQdrantRepository
from chat.core.providers import (
    AnthropicAdapter,
    GeminiAdapter,
    LiteLLMAdapter,
    Mem0Adapter,
    OpenAIAdapter,
    OssFileLoader,
    QwenAdapter,
)
from chat.core.security import SecretCipher
from chat.service_client import FileStorageClient, AIAssetClient, ResourceClient
from common.cloud.service_discovery import ServiceDiscovery
from common.http.rpc_client import RpcClient
from common.kafka.consumer import KafkaConsumerClient
from common.kafka.producer import KafkaProducerClient


async def _provide_nacos_naming() -> NacosNamingService:
    """延迟到首次 await，避免在 import 阶段触发 async Nacos 建连。"""
    return await nacos_client_manager.get_naming_client()


def _build_registry(tool_providers: List[providers.Provider]) -> ToolRegistry:
    registry = ToolRegistry()
    for provider in tool_providers:
        registry.register(provider)
    return registry


def _build_paddle_ocr_client(
        *,
        http_client: httpx.AsyncClient,
) -> PaddleCloudClient | None:
    if not settings.PADDLE_OCR_TOKEN:
        return None

    return PaddleCloudClient(
        config=PaddleCloudConfig(
            api_url=settings.PADDLE_OCR_API_URL,
            token=settings.PADDLE_OCR_TOKEN,
            model=settings.PADDLE_OCR_MODEL,
            timeout_seconds=tool_settings.PADDLE_OCR_TIMEOUT_SECONDS,
            poll_interval_seconds=tool_settings.PADDLE_OCR_POLL_INTERVAL_SECONDS,
            max_poll_attempts=tool_settings.PADDLE_OCR_MAX_POLL_ATTEMPTS,
        ),
        http_client=http_client,
    )


def _build_rag_document_ready_consumer(
        *,
        consumer: RagDocumentReadyConsumer,
) -> KafkaConsumerClient:
    return KafkaConsumerClient(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_DOCUMENT_READY_TOPIC,
        group_id=settings.KAFKA_RAG_DOCUMENT_READY_GROUP_ID,
        handler=consumer.handle,
    )


def _build_rag_acl_recalc_consumer(
        *,
        consumer: RagAclRecalculateConsumer,
) -> KafkaConsumerClient:
    return KafkaConsumerClient(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_RESOURCE_ACL_RECALC_TOPIC,
        group_id=settings.KAFKA_RAG_ACL_RECALC_GROUP_ID,
        handler=consumer.handle,
    )


def _build_elasticsearch_client() -> AsyncElasticsearch | None:
    base_url = settings.ELASTIC_SEARCH_BASE_URL.strip()
    if not base_url:
        return None

    return AsyncElasticsearch(
        base_url,
        basic_auth=(
            settings.ELASTIC_SEARCH_USERNAME,
            settings.ELASTIC_SEARCH_PASSWORD,
        ),
    )


def _build_qdrant_client() -> AsyncQdrantClient | None:
    host = settings.QDRANT_HOST.strip()
    if not host:
        return None

    return AsyncQdrantClient(
        host=host,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_PASSWORD or None,
    )


def _build_qdrant_bm25_config() -> qdrant_models.Bm25Config:
    return qdrant_models.Bm25Config(
        tokenizer=qdrant_models.TokenizerType(settings.QDRANT_RAG_BM25_TOKENIZER),
    )


def _build_platform_default_searcher(
        *,
        http_client: httpx.AsyncClient,
) -> ProviderSearcher:
    return PlatformDefaultSearcher(
        fourget_searcher=FourGetSearcher(
            http_client=http_client,
            config=SearchProviderConfig(
                base_url=settings.WEB_SEARCH_FOURGET_BASE_URL,
                source_id="platform_default",
            ),
        ),
        ddg_searcher=DdgSearcher(),
    )


def _build_web_fetch_http_client() -> httpx.AsyncClient:
    transport = hishel_httpx.AsyncCacheTransport(
        next_transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
    )
    return httpx.AsyncClient(
        timeout=httpx.Timeout(tool_settings.WEB_FETCH_TIMEOUT_SECONDS),
        transport=transport,
        trust_env=False,
    )


class Container(containers.DeclarativeContainer):
    """依赖注入容器，管理单例对象的生命周期。"""
    qwen_adapter = providers.Singleton(QwenAdapter)
    openai_adapter = providers.Singleton(OpenAIAdapter)
    anthropic_adapter = providers.Singleton(AnthropicAdapter)
    gemini_adapter = providers.Singleton(GeminiAdapter)
    litellm_adapter = providers.Singleton(LiteLLMAdapter)
    llm_provider_resolver = providers.Singleton(
        LLMProviderResolver,
        qwen_adapter=qwen_adapter,
        openai_adapter=openai_adapter,
        anthropic_adapter=anthropic_adapter,
        gemini_adapter=gemini_adapter,
        litellm_adapter=litellm_adapter,
    )
    token_counter = providers.Singleton(TokenCounter)
    memory_provider = providers.Singleton(Mem0Adapter)

    session_repo = providers.Singleton(MongoSessionRepository)
    message_repo = providers.Singleton(MongoMessageRepository)
    model_repo = providers.Singleton(MongoModelRepository)
    provider_repo = providers.Singleton(MongoProviderRepository)
    secret_cipher = providers.Singleton(
        SecretCipher,
        encryption_key=settings.SECRET_ENCRYPTION_KEY,
    )
    web_search_credential_repo = providers.Singleton(
        MongoWebSearchCredentialRepository,
        secret_cipher=secret_cipher,
    )
    hot_context_repo = providers.Singleton(RedisHotContext)

    # 内部 RPC：Nacos 服务发现 + 通用 httpx 客户端 + file-storage typed facade
    service_discovery = providers.Singleton(
        ServiceDiscovery,
        naming_client_provider=providers.Object(_provide_nacos_naming),
        group_name=bootstrap_settings.NACOS_GROUP,
        default_strategy=settings.RPC_LB_STRATEGY,
        cache_ttl_seconds=settings.SERVICE_DISCOVERY_CACHE_TTL_SECONDS,
    )
    rpc_client = providers.Singleton(
        RpcClient,
        discovery=service_discovery,
        from_source_secret=settings.FROM_SOURCE_SECRET,
        timeout=settings.RPC_DEFAULT_TIMEOUT,
        retries=settings.RPC_DEFAULT_RETRIES,
        default_strategy=settings.RPC_LB_STRATEGY,
    )
    file_storage_client = providers.Singleton(
        FileStorageClient,
        rpc=rpc_client,
    )
    ai_asset_client = providers.Singleton(
        AIAssetClient,
        rpc=rpc_client,
    )
    resource_client = providers.Singleton(
        ResourceClient,
        rpc=rpc_client,
    )

    # OssFileLoader
    oss_file_loader = providers.Singleton(
        OssFileLoader,
        file_storage_client=file_storage_client,
        cache_dir=settings.OSS_CACHE_DIR,
        cache_ttl_seconds=settings.OSS_CACHE_TTL_SECONDS,
        gc_interval_seconds=settings.OSS_CACHE_GC_INTERVAL_SECONDS,
    )

    # Skill 子系统：
    # - SkillRepository 从 Java ai-asset 读取 Skill
    # DefaultSkillMatcher
    skill_matcher = providers.Singleton(
        DefaultSkillMatcher,
        ai_asset_client=ai_asset_client,
    )
    agent_resolver = providers.Singleton(DefaultAgentResolver)
    kafka_producer = providers.Singleton(
        KafkaProducerClient,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    )
    rag_chunking_service = providers.Singleton(
        RagChunkingService,
    )
    rag_context_indexing_service = providers.Singleton(
        ContextIndexingService,
    )
    rag_embedding_client = providers.Singleton(
        build_embedding_client,
    )
    rag_qdrant_bm25_config = providers.Singleton(
        _build_qdrant_bm25_config,
    )
    rag_corpus_repository = providers.Singleton(
        MongoRagCorpusRepository,
    )
    rag_acl_projection_projector = providers.Singleton(
        RagAclProjectionProjector,
    )
    rag_acl_projection_repository = providers.Singleton(
        MongoRagAclProjectionRepository,
        projector=rag_acl_projection_projector,
    )
    elasticsearch_client = providers.Singleton(
        _build_elasticsearch_client,
    )
    rag_permission_filter_builder = providers.Singleton(
        RagPermissionFilterBuilder,
    )
    qdrant_client = providers.Singleton(
        _build_qdrant_client,
    )
    rag_qdrant_repository = providers.Singleton(
        RagQdrantRepository,
        client=qdrant_client,
        collection_name=settings.QDRANT_RAG_COLLECTION_NAME,
        dense_vector_size=settings.EMBEDDING_DIMENSIONS,
        bm25_config=rag_qdrant_bm25_config,
    )
    rag_elastic_repository = providers.Singleton(
        RagElasticRepository,
        client=elasticsearch_client,
        index_name=settings.ELASTIC_SEARCH_RAG_INDEX_NAME,
    )
    rag_qdrant_retriever = providers.Singleton(
        RagQdrantRetriever,
        client=qdrant_client,
        collection_name=settings.QDRANT_RAG_COLLECTION_NAME,
        permission_filter_builder=rag_permission_filter_builder,
        bm25_config=rag_qdrant_bm25_config,
    )
    rag_elastic_retriever = providers.Singleton(
        RagElasticRetriever,
        client=elasticsearch_client,
        index_name=settings.ELASTIC_SEARCH_RAG_INDEX_NAME,
        permission_filter_builder=rag_permission_filter_builder,
    )
    rag_markdown_ingester = providers.Singleton(
        RagMarkdownIngester,
        chunking_service=rag_chunking_service,
        context_indexing_service=rag_context_indexing_service,
        embedding_client=rag_embedding_client,
        corpus_repository=rag_corpus_repository,
        acl_repository=rag_acl_projection_repository,
        qdrant_repository=rag_qdrant_repository,
        elastic_repository=rag_elastic_repository,
    )
    rag_evidence_ranking_service = providers.Singleton(
        RagEvidenceRankingService,
    )
    rag_evidence_materializer = providers.Singleton(
        RagEvidenceMaterializer,
        corpus_repository=rag_corpus_repository,
    )
    rag_context_builder = providers.Singleton(
        RagContextBuilder,
    )
    rag_answerability_hard_gate = providers.Singleton(
        AnswerabilityHardGate,
    )
    rag_answerability_soft_gate = providers.Singleton(
        AnswerabilitySoftGate,
    )
    rag_hybrid_retriever = providers.Singleton(
        RagHybridRetriever,
        embedding_client=rag_embedding_client,
        elastic_retriever=rag_elastic_retriever,
        qdrant_retriever=rag_qdrant_retriever,
    )
    rag_knowledge_searcher = providers.Singleton(
        RagKnowledgeSearcher,
        retriever=rag_hybrid_retriever,
        ranking_service=rag_evidence_ranking_service,
        hard_gate=rag_answerability_hard_gate,
        soft_gate=rag_answerability_soft_gate,
        evidence_materializer=rag_evidence_materializer,
        context_builder=rag_context_builder,
    )
    rag_document_ready_message_consumer = providers.Singleton(
        RagDocumentReadyConsumer,
        ingester=rag_markdown_ingester,
    )
    rag_document_ready_kafka_consumer = providers.Singleton(
        _build_rag_document_ready_consumer,
        consumer=rag_document_ready_message_consumer,
    )
    rag_acl_projection_updater = providers.Singleton(
        RagAclProjectionUpdater,
        targets=providers.List(
            rag_qdrant_repository,
            rag_elastic_repository,
        ),
    )
    rag_acl_recalculate_message_consumer = providers.Singleton(
        RagAclRecalculateConsumer,
        projector=rag_acl_projection_projector,
        repository=rag_acl_projection_repository,
        updater=rag_acl_projection_updater,
    )
    rag_acl_recalc_kafka_consumer = providers.Singleton(
        _build_rag_acl_recalc_consumer,
        consumer=rag_acl_recalculate_message_consumer,
    )

    # ==================================================================
    # Tool 基础设施：仓储、存储、缓存、渲染、调度
    # ==================================================================
    tool_content_repository = providers.Singleton(
        RedisToolContentRepository,
        redis_url=settings.REDIS_URL,
        ttl_seconds=DEFAULT_TOOL_CONTENT_TTL_SECONDS,
    )
    tool_content_store = providers.Singleton(
        ToolContentStore,
        repository=tool_content_repository,
    )
    tool_run_file_repository = providers.Singleton(
        RedisToolRunFileRepository,
        redis_url=settings.REDIS_URL,
    )
    tool_run_file_store = providers.Singleton(
        ToolRunFileStore,
        repository=tool_run_file_repository,
        root_dir=settings.TOOL_RUN_FILE_ROOT,
        ref_ttl_seconds=tool_settings.TOOL_RUN_FILE_REF_TTL_SECONDS,
        cleanup_grace_seconds=tool_settings.TOOL_RUN_FILE_CLEANUP_GRACE_SECONDS,
        max_file_size_bytes=tool_settings.TOOL_RUN_FILE_MAX_BYTES,
    )
    tool_run_file_store_gc_scheduler = providers.Singleton(
        ToolRunFileStoreGcScheduler,
        store=tool_run_file_store,
    )
    tool_output_renderer = providers.Singleton(ToolOutputRenderer)
    tool_output_cache = providers.Singleton(
        ToolOutputCache,
        content_store=tool_content_store,
        inline_max_chars=settings.TOOL_RESULT_MAX_CHARS,
    )
    tool_dispatcher = providers.Singleton(
        ToolDispatcher,
        output_renderer=tool_output_renderer,
        output_cache=tool_output_cache,
    )

    # ==================================================================
    # Tool 组件：HTTP 客户端、Fetcher、Searcher、Service、Hydrator 等
    # ==================================================================

    # --- Document Parse 组件 ---
    paddle_ocr_http_client = providers.Singleton(
        httpx.AsyncClient,
        timeout=httpx.Timeout(tool_settings.PADDLE_OCR_TIMEOUT_SECONDS),
    )
    paddle_ocr_client = providers.Singleton(
        _build_paddle_ocr_client,
        http_client=paddle_ocr_http_client,
    )
    document_parse_service = providers.Singleton(
        DocumentParseService,
        ocr_client=paddle_ocr_client,
    )

    # --- Web Search 组件 ---
    web_search_http_client = providers.Singleton(
        httpx.AsyncClient,
        timeout=httpx.Timeout(tool_settings.WEB_SEARCH_TIMEOUT_SECONDS),
        trust_env=False,
    )
    platform_default_searcher = providers.Singleton(
        _build_platform_default_searcher,
        http_client=web_search_http_client,
    )
    web_search_runtime_context_resolver = providers.Singleton(
        WebSearchRuntimeContextResolver,
        credential_repository=web_search_credential_repo,
        cipher=secret_cipher,
        platform_member_provider=settings.WEB_SEARCH_PLATFORM_MEMBER_PROVIDER,
        platform_member_api_key=settings.WEB_SEARCH_PLATFORM_MEMBER_API_KEY,
    )
    web_search_integration_searcher_factory = providers.Singleton(
        IntegrationSearcherFactory,
        http_client=web_search_http_client,
        exa_base_url=settings.WEB_SEARCH_EXA_BASE_URL,
        tavily_base_url=settings.WEB_SEARCH_TAVILY_BASE_URL,
        anysearch_base_url=settings.WEB_SEARCH_ANYSEARCH_BASE_URL,
        baidu_qianfan_base_url=settings.WEB_SEARCH_BAIDU_QIANFAN_BASE_URL,
    )
    web_search_custom_source_factory = providers.Singleton(
        WebSearchCustomSourceFactory,
        integration_searcher_factory=web_search_integration_searcher_factory,
    )
    web_search_platform_source_factory = providers.Singleton(
        WebSearchPlatformSourceFactory,
        platform_default_searcher=platform_default_searcher,
        integration_searcher_factory=web_search_integration_searcher_factory,
    )
    web_search_candidate_repository = providers.Singleton(
        RedisWebSearchCandidateRepository,
        redis_url=settings.REDIS_URL,
    )
    web_search_service = providers.Singleton(
        WebSearchService,
    )

    # --- Web Fetch / Crawl 组件 ---
    web_content_cache_entry_repository = providers.Singleton(
        RedisWebContentCacheEntryRepository,
        redis_url=settings.REDIS_URL,
    )
    web_content_cache_value_repository = providers.Singleton(
        MongoWebContentCacheValueRepository,
    )
    web_content_cache_gc_scheduler = providers.Singleton(
        WebContentCacheGcScheduler,
        entry_repository=web_content_cache_entry_repository,
    )
    web_fetch_http_client = providers.Singleton(
        _build_web_fetch_http_client,
    )
    web_fetch_httpx_fetcher = providers.Singleton(
        HttpxFetcher,
        http_client=web_fetch_http_client,
        max_response_bytes=tool_settings.WEB_FETCH_MAX_RESPONSE_BYTES,
    )
    web_fetch_scrapling_fetcher = providers.Singleton(
        ScraplingFetcher,
        timeout_ms=int(tool_settings.WEB_FETCH_TIMEOUT_SECONDS * 1000),
        max_response_bytes=tool_settings.WEB_FETCH_MAX_RESPONSE_BYTES,
    )
    web_fetch_cleaner = providers.Singleton(
        TrafilaturaCleaner,
    )
    web_crawler = providers.Singleton(
        WebCrawler,
        httpx_fetcher=web_fetch_httpx_fetcher,
        scrapling_fetcher=web_fetch_scrapling_fetcher,
        cleaner=web_fetch_cleaner,
        content_cache_entry_repository=web_content_cache_entry_repository,
        content_cache_value_repository=web_content_cache_value_repository,
        min_text_length=tool_settings.WEB_FETCH_MIN_TEXT_LENGTH,
        concurrency=tool_settings.WEB_FETCH_BATCH_CONCURRENCY,
    )
    web_fetch_coordinator = providers.Singleton(
        FetchCoordinator,
        httpx_fetcher=web_fetch_httpx_fetcher,
        scrapling_fetcher=web_fetch_scrapling_fetcher,
        cleaner=web_fetch_cleaner,
        file_store=tool_run_file_store,
        content_cache_entry_repository=web_content_cache_entry_repository,
        content_cache_value_repository=web_content_cache_value_repository,
        min_text_length=tool_settings.WEB_FETCH_MIN_TEXT_LENGTH,
        batch_concurrency=tool_settings.WEB_FETCH_BATCH_CONCURRENCY,
        scrapling_concurrency=tool_settings.WEB_FETCH_SCRAPLING_CONCURRENCY,
        max_scrapling_fallbacks=tool_settings.WEB_FETCH_MAX_SCRAPLING_FALLBACKS,
    )

    # --- Hydrator 组件 ---
    openalex_paper_hydrator = providers.Singleton(
        PaperHydrator,
        http_client=web_search_http_client,
        base_url=settings.OPENALEX_BASE_URL,
    )
    academic_search_service = providers.Singleton(
        AcademicSearchService,
        paper_hydrator=openalex_paper_hydrator,
    )

    # ==================================================================
    # Tool 本身：最终注册到 ToolRegistry 的工具实例
    # ==================================================================

    # --- Math Tools ---
    calculus_solver_tool = providers.Singleton(CalculusSolveTool)
    linear_algebra_solver_tool = providers.Singleton(LinearAlgebraSolveTool)
    equation_solver_tool = providers.Singleton(EquationSolveTool)
    stats_solver_tool = providers.Singleton(StatsSolveTool)
    expression_solver_tool = providers.Singleton(ExpressionSolveTool)

    # --- Document Tools ---
    document_parse_tool = providers.Singleton(
        DocumentParseTool,
        file_store=tool_run_file_store,
        parse_service=document_parse_service,
        content_cache_entry_repository=web_content_cache_entry_repository,
        content_cache_value_repository=web_content_cache_value_repository,
        url_download_http_client=web_fetch_http_client,
    )
    image_ocr_tool = providers.Singleton(
        ImageOcrTool,
        file_store=tool_run_file_store,
        ocr_client=paddle_ocr_client,
        url_download_http_client=web_fetch_http_client,
    )

    # --- Session Tools ---
    search_history_tool = providers.Singleton(
        GetHistoricalChatMessagesTool,
        message_repo=message_repo,
        max_output_chars=settings.TOOL_RESULT_MAX_CHARS,
    )
    tool_content_read_tool = providers.Singleton(
        ToolContentReadTool,
        content_store=tool_content_store,
    )
    tool_content_sequential_read_tool = providers.Singleton(
        ToolContentSequentialReadTool,
        content_store=tool_content_store,
    )

    # --- Web Tools ---
    web_search_tool = providers.Singleton(
        WebSearchTool,
        service=web_search_service,
        custom_source_factory=web_search_custom_source_factory,
        platform_source_factory=web_search_platform_source_factory,
        candidate_repository=web_search_candidate_repository,
    )
    academic_search_tool = providers.Singleton(
        AcademicSearchTool,
        service=academic_search_service,
        custom_source_factory=web_search_custom_source_factory,
        platform_source_factory=web_search_platform_source_factory,
        candidate_repository=web_search_candidate_repository,
    )
    web_crawl_tool = providers.Singleton(
        WebCrawlTool,
        crawler=web_crawler,
    )
    web_fetch_tool = providers.Singleton(
        WebFetchTool,
        service=web_fetch_coordinator,
        candidate_repository=web_search_candidate_repository,
    )

    # --- Skill Tools ---
    load_skill_tool = providers.Singleton(
        LoadSkillTool,
        ai_asset_client=ai_asset_client,
        resource_client=resource_client,
        file_loader=oss_file_loader,
        max_output_chars=settings.TOOL_RESULT_MAX_CHARS,
    )
    load_skill_asset_tool = providers.Singleton(
        LoadSkillAssetTool,
        ai_asset_client=ai_asset_client,
        resource_client=resource_client,
        file_loader=oss_file_loader,
        max_output_chars=settings.TOOL_RESULT_MAX_CHARS,
    )
    # --- Tool Registry ---
    tool_providers = providers.List(
        document_parse_tool,
        image_ocr_tool,
        calculus_solver_tool,
        linear_algebra_solver_tool,
        equation_solver_tool,
        stats_solver_tool,
        expression_solver_tool,
        tool_content_read_tool,
        tool_content_sequential_read_tool,
        web_search_tool,
        academic_search_tool,
        web_crawl_tool,
        web_fetch_tool,
        search_history_tool,
        load_skill_tool,
        load_skill_asset_tool,
    )
    tool_registry = providers.Singleton(
        _build_registry,
        tool_providers=tool_providers,
    )

    # Application 层组件
    chat_turn_coordinator = providers.Factory(
        ChatTurnCoordinator,
        llm_provider_resolver=llm_provider_resolver,
        text_llm=litellm_adapter,
        token_counter=token_counter,
        memory=memory_provider,
        model_repo=model_repo,
        provider_repo=provider_repo,
        session_repo=session_repo,
        message_repo=message_repo,
        hot_context_repo=hot_context_repo,
        tool_registry=tool_registry,
        tool_dispatcher=tool_dispatcher,
        kafka_producer=kafka_producer,
        skill_matcher=skill_matcher,
        agent_resolver=agent_resolver,
        web_search_runtime_context_resolver=web_search_runtime_context_resolver,
    )


# 全局容器实例
container = Container()
