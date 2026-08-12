"""RAG v2 的对象装配容器。

容器只装配已经存在的能力和持久化 port；外部配置通过容器 configuration
注入，避免导入模块时触发 Nacos 或数据库连接。
"""

from dependency_injector import containers, providers
from pymongo import AsyncMongoClient

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.index import ContextualTextIndexer
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
from rag.core.persistence.mongo import (
    MongoAppliedContentReader,
    MongoAppliedRevisionReader,
    MongoAppliedStructureReader,
    MongoAuthoritativeAclReader,
    MongoGenerationCacheStore,
    MongoResourceAclStore,
    MongoSourcePartReader,
)
from rag.core.persistence.qdrant import (
    QdrantCandidateSearch,
    QdrantRetrievalIndexWriter,
)
from rag.core.persistence.redis import RedisNavigationStateStore


def _build_authoritative_resource_collection(
    mongo_client: AsyncMongoClient,
    database_name: str,
):
    return mongo_client[database_name]["wisepen_resource_items"]


def _build_qdrant_bm25_options(tokenizer: str) -> dict[str, str]:
    return {"tokenizer": tokenizer}


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
    contextual_text_client = providers.Dependency()
    contextual_text_indexer = providers.Singleton(
        ContextualTextIndexer,
        client=contextual_text_client,
        cache=generation_cache_store,
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


container = Container()
