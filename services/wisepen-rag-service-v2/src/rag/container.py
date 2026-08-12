"""RAG v2 的对象装配容器。

容器只装配已经存在的能力和持久化 port；外部配置通过容器 configuration
注入，避免导入模块时触发 Nacos 或数据库连接。
"""

import redis.asyncio as redis
from dependency_injector import containers, providers
from neo4j import AsyncGraphDatabase
from pymongo import AsyncMongoClient
from qdrant_client import AsyncQdrantClient
from zeroentropy import AsyncZeroEntropy

from rag.api.kafka import (
    AclRecalculateHandler,
    DocumentReadyHandler,
    KafkaEventConsumer,
    ResourceDestroyHandler,
)
from rag.application.rag.acl import PermissionAuthorizer, ResourceAclRefresher
from rag.application.rag.expand import KnowledgeGraphExpander
from rag.application.rag.index import (
    ContextualTextIndexer,
    KnowledgeGraphExtractor,
    ResourceDeleter,
    ResourceIndexer,
)
from rag.application.rag.index.graph_extraction import QueryClientGraphRagLLM
from rag.application.rag.locate import ReadingEntryLocator
from rag.application.rag.read import (
    DiscoveredSectionReader,
    DocumentContentReader,
    DocumentStructureReader,
)
from rag.application.rag.verify import EvidenceVerifier
from rag.core.config import AppSettings
from rag.core.persistence.mongo import (
    MongoAppliedContentReader,
    MongoAppliedRevisionReader,
    MongoAppliedStructureReader,
    MongoAuthoritativeAclReader,
    MongoEvidenceReader,
    MongoGenerationCacheStore,
    MongoGraphBuildSourceReader,
    MongoResourceAclStore,
    MongoResourceIndexWriter,
    MongoSourcePartReader,
)
from rag.core.persistence.neo4j import (
    Neo4jGraphAclWriter,
    Neo4jGraphTraversal,
    Neo4jKnowledgeGraphWriter,
    Neo4jMentionLookup,
)
from rag.core.persistence.qdrant import (
    QdrantCandidateSearch,
    QdrantRetrievalAclWriter,
    QdrantRetrievalIndexWriter,
)
from rag.core.persistence.redis import RedisNavigationStateStore
from rag.utils.llm_clients import EmbeddingClient, QueryClient
from rag.utils.ranking import RankingPipeline
from rag.utils.ranking.diversifiers import MmrDiversifier, MmrDiversifierConfig
from rag.utils.ranking.fusion import WeightedRrfFusion
from rag.utils.ranking.relevance_gate import (
    HighLowRelevanceGate,
    HighLowRelevanceGateConfig,
)
from rag.utils.ranking.rerankers import (
    ZeroEntropyReranker,
    ZeroEntropyRerankerConfig,
)
from rag.utils.ranking.scorers import (
    BM25Scorer,
    FieldedBM25Scorer,
    FieldedBM25ScorerConfig,
)
from rag.utils.ranking.tokenizer import ThuLacRankingTokenizer


def _build_authoritative_resource_collection(
    mongo_client: AsyncMongoClient,
    database_name: str,
):
    return mongo_client[database_name]["wisepen_resource_items"]


def _build_qdrant_bm25_options(tokenizer: str) -> dict[str, str]:
    return {"tokenizer": tokenizer}


def _build_qdrant_client(
    *,
    host: str,
    port: int,
    api_key: str,
) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        host=host,
        port=port,
        api_key=api_key or None,
        https=False,
        cloud_inference=True,
        check_compatibility=False,
    )


def _build_kafka_consumer(
    *,
    bootstrap_servers: str,
    topic: str,
    group_id: str,
    handler,
) -> KafkaEventConsumer:
    return KafkaEventConsumer(
        bootstrap_servers=bootstrap_servers,
        topic=topic,
        group_id=group_id,
        handler=handler.handle,
    )


def _build_locate_ranking_pipeline(
    *,
    zero_entropy_client: AsyncZeroEntropy,
    reranker_model: str,
    low_watermark: float,
    high_watermark: float,
    uncertain_limit: int,
) -> RankingPipeline:
    tokenizer = ThuLacRankingTokenizer()
    return RankingPipeline(
        fusion=WeightedRrfFusion(),
        reranker=ZeroEntropyReranker(
            client=zero_entropy_client,
            config=ZeroEntropyRerankerConfig(model=reranker_model),
        ),
        gate=HighLowRelevanceGate(
            HighLowRelevanceGateConfig(
                low_watermark=low_watermark,
                high_watermark=high_watermark,
                uncertain_limit=uncertain_limit,
            )
        ),
        diversifiers=(
            MmrDiversifier(
                tokenizer=tokenizer,
                config=MmrDiversifierConfig(
                    lambda_mult=0.78,
                    same_group_similarity=0.95,
                ),
            ),
        ),
    )


def _build_expand_ranking_pipeline(
    *,
    zero_entropy_client: AsyncZeroEntropy,
    reranker_model: str,
) -> RankingPipeline:
    tokenizer = ThuLacRankingTokenizer()
    return RankingPipeline(
        scorers=(
            BM25Scorer(tokenizer=tokenizer),
            FieldedBM25Scorer(
                tokenizer=tokenizer,
                config=FieldedBM25ScorerConfig(
                    field_weights={"nodes": 2.0, "relations": 2.0},
                ),
            ),
        ),
        fusion=WeightedRrfFusion(),
        reranker=ZeroEntropyReranker(
            client=zero_entropy_client,
            config=ZeroEntropyRerankerConfig(model=reranker_model),
        ),
    )


class Container(containers.DeclarativeContainer):
    """管理 RAG application 对象及其持久化 port 的单例依赖。"""

    config = providers.Configuration()

    applied_revision_reader = providers.Singleton(MongoAppliedRevisionReader)
    source_part_reader = providers.Singleton(MongoSourcePartReader)
    applied_structure_reader = providers.Singleton(
        MongoAppliedStructureReader,
        revisions=applied_revision_reader,
    )
    applied_content_reader = providers.Singleton(
        MongoAppliedContentReader,
        revisions=applied_revision_reader,
        source_parts=source_part_reader,
    )
    evidence_reader = providers.Singleton(
        MongoEvidenceReader,
        revisions=applied_revision_reader,
        source_parts=source_part_reader,
    )
    evidence_verifier = providers.Singleton(
        EvidenceVerifier,
        reader=evidence_reader,
    )

    mongo_client = providers.Singleton(AsyncMongoClient, config.mongodb_url)
    authoritative_resource_collection = providers.Singleton(
        _build_authoritative_resource_collection,
        mongo_client=mongo_client,
        database_name=config.resource_permission_database_name,
    )
    authoritative_acl_reader = providers.Singleton(
        MongoAuthoritativeAclReader,
        collection=authoritative_resource_collection,
    )
    resource_acl_store = providers.Singleton(MongoResourceAclStore)
    generation_cache_store = providers.Singleton(MongoGenerationCacheStore)
    graph_build_source_reader = providers.Singleton(
        MongoGraphBuildSourceReader,
        revisions=applied_revision_reader,
        source_parts=source_part_reader,
    )
    contextual_text_client = providers.Dependency()
    contextual_text_indexer = providers.Singleton(
        ContextualTextIndexer,
        client=contextual_text_client,
        cache=generation_cache_store,
    )
    graph_query_client = providers.Dependency()
    graph_llm = providers.Singleton(
        QueryClientGraphRagLLM,
        client=graph_query_client,
    )
    knowledge_graph_extractor = providers.Singleton(
        KnowledgeGraphExtractor,
        llm=graph_llm,
        cache=generation_cache_store,
        source_reader=graph_build_source_reader,
        max_concurrency=config.knowledge_graph_extraction_max_concurrency,
    )
    neo4j_driver = providers.Singleton(
        AsyncGraphDatabase.driver,
        uri=config.neo4j_uri,
        auth=(config.neo4j_user, config.neo4j_password),
    )
    knowledge_graph_writer = providers.Singleton(
        Neo4jKnowledgeGraphWriter,
        driver=neo4j_driver,
        database=config.neo4j_database,
    )
    qdrant_client = providers.Singleton(
        _build_qdrant_client,
        host=config.qdrant_host,
        port=config.qdrant_port,
        api_key=config.qdrant_password,
    )
    qdrant_bm25_options = providers.Factory(
        _build_qdrant_bm25_options,
        tokenizer=config.qdrant_bm25_tokenizer,
    )
    retrieval_index_writer = providers.Singleton(
        QdrantRetrievalIndexWriter,
        client=qdrant_client,
        collection_name=config.qdrant_collection_name,
        dense_vector_size=config.embedding_dimensions,
        embedding_profile=config.embedding_profile,
        dense_vector_name=config.qdrant_dense_vector_name,
        sparse_vector_name=config.qdrant_sparse_vector_name,
        bm25_options=qdrant_bm25_options,
    )
    resource_index_writer = providers.Singleton(MongoResourceIndexWriter)
    retrieval_acl_writer = providers.Singleton(
        QdrantRetrievalAclWriter,
        client=qdrant_client,
        collection_name=config.qdrant_collection_name,
    )
    candidate_search = providers.Singleton(
        QdrantCandidateSearch,
        client=qdrant_client,
        collection_name=config.qdrant_collection_name,
        dense_vector_size=config.embedding_dimensions,
        dense_vector_name=config.qdrant_dense_vector_name,
        sparse_vector_name=config.qdrant_sparse_vector_name,
        bm25_options=qdrant_bm25_options,
    )
    redis_client = providers.Singleton(
        redis.from_url,
        config.redis_url,
        decode_responses=True,
    )
    navigation_state_store = providers.Singleton(
        RedisNavigationStateStore,
        redis_client=redis_client,
        ttl_seconds=config.navigation_state_ttl_seconds,
    )
    permission_authorizer = providers.Singleton(
        PermissionAuthorizer,
        reader=resource_acl_store,
    )
    document_structure_reader = providers.Singleton(
        DocumentStructureReader,
        reader=applied_structure_reader,
        authorizer=permission_authorizer,
    )
    document_content_reader = providers.Singleton(
        DocumentContentReader,
        reader=applied_content_reader,
        authorizer=permission_authorizer,
    )
    graph_acl_writer = providers.Singleton(
        Neo4jGraphAclWriter,
        driver=neo4j_driver,
        database=config.neo4j_database,
    )
    resource_acl_refresher = providers.Singleton(
        ResourceAclRefresher,
        authoritative_reader=authoritative_acl_reader,
        local_store=resource_acl_store,
        retrieval_writer=retrieval_acl_writer,
        graph_writer=graph_acl_writer,
    )
    embedding_client = providers.Singleton(
        EmbeddingClient,
        model=config.embedding_model,
        api_base=config.llm_base_url,
        api_key=config.llm_api_key,
        dimensions=config.embedding_dimensions,
    )
    resource_indexer = providers.Singleton(
        ResourceIndexer,
        contextual_text=contextual_text_indexer,
        embedding_client=embedding_client,
        acl_refresher=resource_acl_refresher,
        acl_reader=resource_acl_store,
        resource_writer=resource_index_writer,
        retrieval_writer=retrieval_index_writer,
        graph_extractor=knowledge_graph_extractor,
        graph_writer=knowledge_graph_writer,
    )
    resource_deleter = providers.Singleton(
        ResourceDeleter,
        resource_writer=resource_index_writer,
        retrieval_writer=retrieval_index_writer,
        graph_writer=knowledge_graph_writer,
        generation_cache=generation_cache_store,
        acl_store=resource_acl_store,
    )
    discovered_section_reader = providers.Singleton(
        DiscoveredSectionReader,
        content_reader=applied_content_reader,
        revision_reader=applied_revision_reader,
        authorizer=permission_authorizer,
        state_store=navigation_state_store,
    )
    mention_lookup = providers.Singleton(
        Neo4jMentionLookup,
        driver=neo4j_driver,
        database=config.neo4j_database,
        authorizer=permission_authorizer,
    )
    graph_traversal = providers.Singleton(
        Neo4jGraphTraversal,
        driver=neo4j_driver,
        database=config.neo4j_database,
        authorizer=permission_authorizer,
    )
    zero_entropy_client = providers.Singleton(
        AsyncZeroEntropy,
        api_key=config.zero_entropy_api_key,
    )
    locate_ranking_pipeline = providers.Singleton(
        _build_locate_ranking_pipeline,
        zero_entropy_client=zero_entropy_client,
        reranker_model=config.reranker_model,
        low_watermark=config.rerank_relevance_low_watermark,
        high_watermark=config.rerank_relevance_high_watermark,
        uncertain_limit=config.rerank_uncertain_limit,
    )
    expand_ranking_pipeline = providers.Singleton(
        _build_expand_ranking_pipeline,
        zero_entropy_client=zero_entropy_client,
        reranker_model=config.reranker_model,
    )
    reading_entry_locator = providers.Singleton(
        ReadingEntryLocator,
        embedding_client=embedding_client,
        candidate_search=candidate_search,
        ranking_pipeline=locate_ranking_pipeline,
        authorizer=permission_authorizer,
        evidence_verifier=evidence_verifier,
        mention_lookup=mention_lookup,
        revision_reader=applied_revision_reader,
        structure_reader=applied_structure_reader,
        state_store=navigation_state_store,
    )
    knowledge_graph_expander = providers.Singleton(
        KnowledgeGraphExpander,
        traversal=graph_traversal,
        ranking_pipeline=expand_ranking_pipeline,
        evidence_verifier=evidence_verifier,
        state_store=navigation_state_store,
    )

    document_ready_handler = providers.Singleton(
        DocumentReadyHandler,
        indexer=resource_indexer,
    )
    acl_recalculate_handler = providers.Singleton(
        AclRecalculateHandler,
        refresher=resource_acl_refresher,
    )
    resource_destroy_handler = providers.Singleton(
        ResourceDestroyHandler,
        deleter=resource_deleter,
    )
    document_ready_consumer = providers.Singleton(
        _build_kafka_consumer,
        bootstrap_servers=config.kafka_bootstrap_servers,
        topic=config.kafka_document_ready_topic,
        group_id=config.kafka_document_ready_group_id,
        handler=document_ready_handler,
    )
    acl_recalculate_consumer = providers.Singleton(
        _build_kafka_consumer,
        bootstrap_servers=config.kafka_bootstrap_servers,
        topic=config.kafka_acl_recalculate_topic,
        group_id=config.kafka_acl_recalculate_group_id,
        handler=acl_recalculate_handler,
    )
    resource_destroy_consumer = providers.Singleton(
        _build_kafka_consumer,
        bootstrap_servers=config.kafka_bootstrap_servers,
        topic=config.kafka_resource_destroy_topic,
        group_id=config.kafka_resource_destroy_group_id,
        handler=resource_destroy_handler,
    )


container = Container()


def configure_container(target: Container, settings: AppSettings) -> None:
    """把一次启动读取到的配置显式注入对象图，不保留模块级 settings。"""
    target.config.from_dict(
        {
            "mongodb_url": settings.MONGODB_URL,
            "resource_permission_database_name": (
                settings.RESOURCE_PERMISSION_MONGODB_DB_NAME
            ),
            "llm_base_url": settings.LLM_BASE_URL,
            "llm_api_key": settings.LLM_API_KEY,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
            "embedding_profile": settings.EMBEDDING_MODEL,
            "knowledge_graph_extraction_max_concurrency": (
                settings.KNOWLEDGE_GRAPH_EXTRACTION_MAX_CONCURRENCY
            ),
            "neo4j_uri": settings.NEO4J_URI,
            "neo4j_user": settings.NEO4J_USER,
            "neo4j_password": settings.NEO4J_PASSWORD,
            "neo4j_database": settings.NEO4J_DATABASE,
            "qdrant_host": settings.QDRANT_HOST,
            "qdrant_port": settings.QDRANT_PORT,
            "qdrant_password": settings.QDRANT_PASSWORD,
            "qdrant_collection_name": settings.QDRANT_RAG_COLLECTION_NAME,
            "qdrant_dense_vector_name": settings.QDRANT_RAG_DENSE_VECTOR_NAME,
            "qdrant_sparse_vector_name": settings.QDRANT_RAG_SPARSE_VECTOR_NAME,
            "qdrant_bm25_tokenizer": settings.QDRANT_RAG_BM25_TOKENIZER,
            "redis_url": settings.REDIS_URL,
            "navigation_state_ttl_seconds": (
                settings.RAG_NAVIGATION_STATE_TTL_SECONDS
            ),
            "zero_entropy_api_key": settings.ZERO_ENTROPY_API_KEY,
            "reranker_model": settings.RERANKER_MODEL,
            "rerank_relevance_low_watermark": (
                settings.RAG_RERANK_RELEVANCE_LOW_WATERMARK
            ),
            "rerank_relevance_high_watermark": (
                settings.RAG_RERANK_RELEVANCE_HIGH_WATERMARK
            ),
            "rerank_uncertain_limit": settings.RAG_RERANK_UNCERTAIN_LIMIT,
            "kafka_bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "kafka_document_ready_topic": settings.KAFKA_DOCUMENT_READY_TOPIC,
            "kafka_document_ready_group_id": (
                settings.KAFKA_RAG_DOCUMENT_READY_GROUP_ID
            ),
            "kafka_acl_recalculate_topic": (
                settings.KAFKA_RESOURCE_ACL_RECALC_TOPIC
            ),
            "kafka_acl_recalculate_group_id": (
                settings.KAFKA_RAG_ACL_RECALC_GROUP_ID
            ),
            "kafka_resource_destroy_topic": (
                settings.KAFKA_RESOURCE_PHYSICAL_DESTROY_TOPIC
            ),
            "kafka_resource_destroy_group_id": (
                settings.KAFKA_RAG_RESOURCE_DESTROY_GROUP_ID
            ),
        }
    )
    target.contextual_text_client.override(
        QueryClient(
            model=settings.QUERY_MODEL,
            api_base=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            thinking="disabled",
        )
    )
    target.graph_query_client.override(
        QueryClient(
            model=settings.QUERY_MODEL,
            api_base=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )
    )
