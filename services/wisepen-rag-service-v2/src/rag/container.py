"""RAG v2 的对象装配容器。

容器只装配已经存在的能力和持久化 port；外部配置通过容器 configuration
注入，避免导入模块时触发 Nacos 或数据库连接。
"""

from dependency_injector import containers, providers
from pymongo import AsyncMongoClient

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
from rag.core.persistence.mongo import (
    MongoAppliedContentReader,
    MongoAppliedRevisionReader,
    MongoAppliedStructureReader,
    MongoAuthoritativeAclReader,
    MongoResourceAclStore,
    MongoSourcePartReader,
)


def _build_authoritative_resource_collection(
    mongo_client: AsyncMongoClient,
    database_name: str,
):
    return mongo_client[database_name]["wisepen_resource_items"]


class Container(containers.DeclarativeContainer):
    """管理 RAG READ/ACL 对象的单例依赖。"""

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
    permission_authorizer = providers.Singleton(
        PermissionAuthorizer,
        reader=resource_acl_store,
    )


container = Container()
