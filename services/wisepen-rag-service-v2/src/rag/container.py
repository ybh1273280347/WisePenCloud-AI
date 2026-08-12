"""RAG v2 的对象装配容器。

容器只装配已经存在的能力和持久化 port；外部配置通过容器 configuration
注入，避免导入模块时触发 Nacos 或数据库连接。
"""

from dependency_injector import containers, providers
from neo4j import AsyncGraphDatabase
from pymongo import AsyncMongoClient
from zeroentropy import AsyncZeroEntropy

from rag.application.rag.acl import PermissionAuthorizer, ResourceAclRefresher
from rag.application.rag.expand import KnowledgeGraphExpander
from rag.application.rag.index import ContextualTextIndexer, KnowledgeGraphExtractor
from rag.application.rag.index.graph_extraction import QueryClientGraphRagLLM
from rag.application.rag.locate import ReadingEntryLocator
from rag.application.rag.read import (
    DiscoveredSectionReader,
    DocumentContentReader,
    DocumentStructureReader,
)
from rag.application.rag.verify import EvidenceVerifier
from rag.core.persistence.mongo import (
    MongoAppliedContentReader,
    MongoAppliedRevisionReader,
    MongoAppliedStructureReader,
    MongoAuthoritativeAclReader,
    MongoEvidenceReader,
    MongoGenerationCacheStore,
    MongoGraphBuildSourceReader,
    MongoResourceAclStore,
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

    document_structure_reader = providers.Singleton(
        DocumentStructureReader,
        reader=applied_structure_reader,
    )
    document_content_reader = providers.Singleton(
        DocumentContentReader,
        reader=applied_content_reader,
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
    qdrant_client = providers.Dependency()
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
    redis_client = providers.Dependency()
    navigation_state_store = providers.Singleton(
        RedisNavigationStateStore,
        redis_client=redis_client,
        ttl_seconds=config.navigation_state_ttl_seconds,
    )
    permission_authorizer = providers.Singleton(
        PermissionAuthorizer,
        reader=resource_acl_store,
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
    embedding_client = providers.Dependency()
    zero_entropy_client = providers.Dependency()
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


container = Container()
