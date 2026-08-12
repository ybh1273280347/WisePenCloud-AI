from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.read import DocumentContentReader, DocumentStructureReader
from rag.container import Container


def test_container_builds_read_objects_with_explicit_persistence_dependencies() -> None:
    container = Container()
    container.config.mongodb_url.from_value("mongodb://localhost:27017")
    container.config.resource_permission_database_name.from_value("permissions")

    assert isinstance(container.document_structure_reader(), DocumentStructureReader)
    assert isinstance(container.document_content_reader(), DocumentContentReader)
    assert isinstance(container.permission_authorizer(), PermissionAuthorizer)
