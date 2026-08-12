"""RAG v2 的对象装配容器。

容器只装配已经存在的能力和持久化 port；外部配置通过容器 configuration
注入，避免导入模块时触发 Nacos 或数据库连接。
"""

from dependency_injector import containers, providers
from pymongo import AsyncMongoClient
from zeroentropy import AsyncZeroEntropy

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.index import ContextualTextIndexer, KnowledgeGraphExtractor
from rag.application.rag.index.graph_extraction import QueryClientGraphRagLLM
from rag.application.rag.locate import ReadingEntryLocator
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
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
from rag.core.persistence.qdrant import (
    QdrantCandidateSearch,
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
    reading_entry_locator = providers.Singleton(
        ReadingEntryLocator,
        embedding_client=embedding_client,
        candidate_search=candidate_search,
        ranking_pipeline=locate_ranking_pipeline,
        authorizer=permission_authorizer,
        evidence_verifier=evidence_verifier,
        revision_reader=applied_revision_reader,
        structure_reader=applied_structure_reader,
        state_store=navigation_state_store,
    )


container = Container()
