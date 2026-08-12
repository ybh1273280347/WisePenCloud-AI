"""内容 revision 身份与 staged 决策规则。"""

from hashlib import sha256

from rag.domain.models.content import ContentRevision, ResourceIndexState
from rag.domain.models.structure import DocumentStructure
from rag.domain.repositories.mongo.writers.resource_index import StageAction

INDEX_SCHEMA_VERSION = "rag-v2-content:v1"


def create_content_revision(
    *,
    resource_id: str,
    document_version: int,
    markdown: str,
    structure: DocumentStructure,
    index_schema_version: str = INDEX_SCHEMA_VERSION,
) -> ContentRevision:
    """以资源、上游版本、原文和 schema 共同确定 revision 身份。"""
    if not resource_id:
        raise ValueError("resource_id must not be empty")
    if document_version < 1:
        raise ValueError("document_version must be positive")
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    if not index_schema_version:
        raise ValueError("index_schema_version must not be empty")

    content_hash = sha256(markdown.encode("utf-8")).hexdigest()
    content_revision = build_content_revision_id(
        resource_id=resource_id,
        document_version=document_version,
        markdown=markdown,
        index_schema_version=index_schema_version,
    )
    return ContentRevision(
        resource_id=resource_id,
        content_revision=content_revision,
        document_version=document_version,
        content_hash=content_hash,
        index_schema_version=index_schema_version,
        structure_mode=structure.mode,
        total_length=len(markdown),
        pages=list(structure.pages),
    )


def build_content_revision_id(
    *,
    resource_id: str,
    document_version: int,
    markdown: str,
    index_schema_version: str = INDEX_SCHEMA_VERSION,
) -> str:
    """在结构解析前确定 revision，使所有派生身份使用同一命名空间。"""
    if not resource_id:
        raise ValueError("resource_id must not be empty")
    if document_version < 1:
        raise ValueError("document_version must be positive")
    if not index_schema_version:
        raise ValueError("index_schema_version must not be empty")

    content_hash = sha256(markdown.encode("utf-8")).hexdigest()
    identity = "\0".join(
        (resource_id, str(document_version), content_hash, index_schema_version)
    )
    return f"rrev_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def decide_stage(
    revision: ContentRevision,
    state: ResourceIndexState | None,
) -> StageAction:
    if state is None:
        return StageAction.STAGED
    if state.resource_id != revision.resource_id:
        raise ValueError("resource index state belongs to another resource")
    if state.applied_content_revision == revision.content_revision:
        return StageAction.ALREADY_APPLIED
    if (
        state.applied_document_version is not None
        and state.applied_document_version > revision.document_version
    ):
        return StageAction.STALE
    if (
        state.staged_document_version is not None
        and state.staged_document_version > revision.document_version
    ):
        return StageAction.STALE
    return StageAction.STAGED
