"""RAG v2 的对象装配容器。"""

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
from rag.api.resource_deletion import ResourceDeletionService
from rag.application.rag.acl import PermissionAuthorizer, ResourceAclRefresher
from rag.application.rag.expand import KnowledgeGraphExpander, SectionTreeExpander
from rag.application.rag.index import KnowledgeGraphExtractor, ResourceIndexer
from rag.application.rag.index.contextualize import ContextualTextIndexer
from rag.application.rag.index.graph_extraction import QueryClientGraphRagLLM
from rag.application.rag.locate import ReadingEntryLocator
from rag.application.rag.read import (
    DocumentContentReader,
    DocumentStructureReader,
)
from rag.application.rag.verify import EvidenceVerifier
from rag.core.config import settings
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

    mongo_client = providers.Singleton(AsyncMongoClient, settings.MONGODB_URL)
    authoritative_resource_collection = providers.Singleton(
        _build_authoritative_resource_collection,
        mongo_client=mongo_client,
        database_name=settings.RESOURCE_PERMISSION_MONGODB_DB_NAME,
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
    contextual_text_client = providers.Singleton(
        QueryClient,
        model=settings.QUERY_MODEL,
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        thinking="disabled",
    )
    contextual_text_indexer = providers.Singleton(
        ContextualTextIndexer,
        client=contextual_text_client,
        cache=generation_cache_store,
    )
    graph_query_client = providers.Singleton(
        QueryClient,
        model=settings.QUERY_MODEL,
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
    )
    graph_llm = providers.Singleton(
        QueryClientGraphRagLLM,
        client=graph_query_client,
    )
    knowledge_graph_extractor = providers.Singleton(
        KnowledgeGraphExtractor,
        llm=graph_llm,
        cache=generation_cache_store,
        source_reader=graph_build_source_reader,
        max_concurrency=settings.KNOWLEDGE_GRAPH_EXTRACTION_MAX_CONCURRENCY,
    )
    neo4j_driver = providers.Singleton(
        AsyncGraphDatabase.driver,
        uri=settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    knowledge_graph_writer = providers.Singleton(
        Neo4jKnowledgeGraphWriter,
        driver=neo4j_driver,
        database=settings.NEO4J_DATABASE,
    )
    qdrant_client = providers.Singleton(
        _build_qdrant_client,
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_PASSWORD,
    )
    qdrant_bm25_options = providers.Factory(
        _build_qdrant_bm25_options,
        tokenizer=settings.QDRANT_RAG_BM25_TOKENIZER,
    )
    retrieval_index_writer = providers.Singleton(
        QdrantRetrievalIndexWriter,
        client=qdrant_client,
        collection_name=settings.QDRANT_RAG_COLLECTION_NAME,
        dense_vector_size=settings.EMBEDDING_DIMENSIONS,
        embedding_profile=settings.EMBEDDING_MODEL,
        dense_vector_name=settings.QDRANT_RAG_DENSE_VECTOR_NAME,
        sparse_vector_name=settings.QDRANT_RAG_SPARSE_VECTOR_NAME,
        bm25_options=qdrant_bm25_options,
    )
    resource_index_writer = providers.Singleton(MongoResourceIndexWriter)
    retrieval_acl_writer = providers.Singleton(
        QdrantRetrievalAclWriter,
        client=qdrant_client,
        collection_name=settings.QDRANT_RAG_COLLECTION_NAME,
    )
    candidate_search = providers.Singleton(
        QdrantCandidateSearch,
        client=qdrant_client,
        collection_name=settings.QDRANT_RAG_COLLECTION_NAME,
        dense_vector_size=settings.EMBEDDING_DIMENSIONS,
        dense_vector_name=settings.QDRANT_RAG_DENSE_VECTOR_NAME,
        sparse_vector_name=settings.QDRANT_RAG_SPARSE_VECTOR_NAME,
        bm25_options=qdrant_bm25_options,
    )
    redis_client = providers.Singleton(
        redis.from_url,
        settings.REDIS_URL,
        decode_responses=True,
    )
    navigation_state_store = providers.Singleton(
        RedisNavigationStateStore,
        redis_client=redis_client,
        ttl_seconds=settings.RAG_NAVIGATION_STATE_TTL_SECONDS,
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
        database=settings.NEO4J_DATABASE,
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
        model=settings.EMBEDDING_MODEL,
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        dimensions=settings.EMBEDDING_DIMENSIONS,
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
    resource_deletion_service = providers.Singleton(
        ResourceDeletionService,
        resource_writer=resource_index_writer,
        retrieval_writer=retrieval_index_writer,
        graph_writer=knowledge_graph_writer,
        generation_cache=generation_cache_store,
        acl_store=resource_acl_store,
    )
    section_tree_expander = providers.Singleton(
        SectionTreeExpander,
        content_reader=applied_content_reader,
        revision_reader=applied_revision_reader,
        authorizer=permission_authorizer,
        state_store=navigation_state_store,
    )
    mention_lookup = providers.Singleton(
        Neo4jMentionLookup,
        driver=neo4j_driver,
        database=settings.NEO4J_DATABASE,
        authorizer=permission_authorizer,
    )
    graph_traversal = providers.Singleton(
        Neo4jGraphTraversal,
        driver=neo4j_driver,
        database=settings.NEO4J_DATABASE,
        authorizer=permission_authorizer,
    )
    zero_entropy_client = providers.Singleton(
        AsyncZeroEntropy,
        api_key=settings.ZERO_ENTROPY_API_KEY,
    )
    locate_ranking_pipeline = providers.Singleton(
        _build_locate_ranking_pipeline,
        zero_entropy_client=zero_entropy_client,
        reranker_model=settings.RERANKER_MODEL,
        low_watermark=settings.RAG_RERANK_RELEVANCE_LOW_WATERMARK,
        high_watermark=settings.RAG_RERANK_RELEVANCE_HIGH_WATERMARK,
        uncertain_limit=settings.RAG_RERANK_UNCERTAIN_LIMIT,
    )
    expand_ranking_pipeline = providers.Singleton(
        _build_expand_ranking_pipeline,
        zero_entropy_client=zero_entropy_client,
        reranker_model=settings.RERANKER_MODEL,
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
        deleter=resource_deletion_service,
    )
    document_ready_consumer = providers.Singleton(
        _build_kafka_consumer,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_DOCUMENT_READY_TOPIC,
        group_id=settings.KAFKA_RAG_DOCUMENT_READY_GROUP_ID,
        handler=document_ready_handler,
    )
    acl_recalculate_consumer = providers.Singleton(
        _build_kafka_consumer,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_RESOURCE_ACL_RECALC_TOPIC,
        group_id=settings.KAFKA_RAG_ACL_RECALC_GROUP_ID,
        handler=acl_recalculate_handler,
    )
    resource_destroy_consumer = providers.Singleton(
        _build_kafka_consumer,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_RESOURCE_PHYSICAL_DESTROY_TOPIC,
        group_id=settings.KAFKA_RAG_RESOURCE_DESTROY_GROUP_ID,
        handler=resource_destroy_handler,
    )


container = Container()
