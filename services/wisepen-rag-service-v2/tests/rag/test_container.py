from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.index import ContextualTextIndexer
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
from rag.container import Container
from rag.core.persistence.mongo import MongoGenerationCacheStore
from rag.core.persistence.qdrant import (
    QdrantCandidateSearch,
    QdrantRetrievalIndexWriter,
)


def test_container_builds_read_objects_with_explicit_persistence_dependencies() -> None:
    container = Container()
    container.config.mongodb_url.from_value("mongodb://localhost:27017")
    container.config.resource_permission_database_name.from_value("permissions")

    assert isinstance(container.document_structure_reader(), DocumentStructureReader)
    assert isinstance(container.document_content_reader(), DocumentContentReader)
    assert isinstance(container.permission_authorizer(), PermissionAuthorizer)
    assert isinstance(container.generation_cache_store(), MongoGenerationCacheStore)

    container.contextual_text_client.override(object())
    assert isinstance(container.contextual_text_indexer(), ContextualTextIndexer)

    container.qdrant_client.override(object())
    container.config.qdrant_collection_name.from_value("retrieval-chunks")
    container.config.embedding_dimensions.from_value(3)
    container.config.embedding_profile.from_value("embedding-v1")
    container.config.qdrant_dense_vector_name.from_value("dense")
    container.config.qdrant_sparse_vector_name.from_value("sparse")
    container.config.qdrant_bm25_tokenizer.from_value("multilingual")
    assert isinstance(container.retrieval_index_writer(), QdrantRetrievalIndexWriter)
    assert isinstance(container.candidate_search(), QdrantCandidateSearch)
