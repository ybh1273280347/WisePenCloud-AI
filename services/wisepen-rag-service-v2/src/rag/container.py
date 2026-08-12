"""RAG v2 的对象装配容器。

容器只装配已经存在的能力和持久化 port。ACL 本地存储尚未进入 CP09，
因此由调用方通过 ``resource_acl_reader`` 覆盖 CP10 的真实 adapter。
"""

from dependency_injector import containers, providers

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
from rag.core.persistence.mongo import (
    MongoAppliedContentReader,
    MongoAppliedRevisionReader,
    MongoAppliedStructureReader,
    MongoSourcePartReader,
)


class Container(containers.DeclarativeContainer):
    """管理 RAG READ/ACL 对象的单例依赖。"""

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

    resource_acl_reader = providers.Dependency()
    permission_authorizer = providers.Singleton(
        PermissionAuthorizer,
        reader=resource_acl_reader,
    )


container = Container()
