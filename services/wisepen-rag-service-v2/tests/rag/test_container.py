from dependency_injector import providers

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
from rag.container import Container


class _MissingAclReader:
    async def get_resource_acls(self, resource_ids):
        return {}


def test_container_builds_read_objects_with_explicit_persistence_dependencies() -> None:
    container = Container()
    container.resource_acl_reader.override(providers.Object(_MissingAclReader()))

    assert isinstance(container.document_structure_reader(), DocumentStructureReader)
    assert isinstance(container.document_content_reader(), DocumentContentReader)
    assert isinstance(container.permission_authorizer(), PermissionAuthorizer)
