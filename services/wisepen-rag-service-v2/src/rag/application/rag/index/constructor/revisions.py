"""内容 revision 身份与 staged 决策规则。

content_revision 是资源在某个上游版本 + 某个索引 schema 下的“内容身份”，
所有派生身份（Section / ReadingBlock / RetrievalChunk / SourceRef）都以它为命名空间，
保证同一内容重复索引时所有派生 ID 完全一致，可安全复用缓存。
"""

from hashlib import sha256

from rag.domain.models.content import ContentRevision
from rag.domain.models.structure import DocumentStructure

# 当前内容索引 schema 版本，参与 content_revision 计算；
# 当索引规则（chunker、结构解析、字段集合）发生变化时递增，强制旧 revision 失效。
INDEX_SCHEMA_VERSION = "rag-v2-content:v2"


def create_content_revision(
    *,
    resource_id: str,
    document_version: int,
    markdown: str,
    structure: DocumentStructure,
    index_schema_version: str = INDEX_SCHEMA_VERSION,
) -> ContentRevision:
    """以资源、上游版本、原文和 schema 共同确定 revision 身份。

    参数:
        resource_id: 资源唯一标识。
        document_version: 上游文档版本号（必须 >= 1）。
        markdown: 权威 Markdown 原文；其长度必须与 ``structure.total_length`` 一致。
        structure: 已解析的文档结构，用于校验长度一致性并提取页面信息。
        index_schema_version: 索引 schema 版本；变更后所有派生 ID 会随之改变。

    返回:
        ``ContentRevision`` 实例，包含 revision ID、内容哈希、结构模式、页面列表等元信息。
    """
    if not resource_id:
        raise ValueError("resource_id must not be empty")
    if document_version < 1:
        raise ValueError("document_version must be positive")
    # structure 与 markdown 必须对应同一份原文，否则派生身份会失去意义。
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    if not index_schema_version:
        raise ValueError("index_schema_version must not be empty")

    # content_hash 仅用于内容比对（与 revision ID 用途不同），不参与身份计算。
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
        anchors=list(structure.anchors),
    )


def build_content_revision_id(
    *,
    resource_id: str,
    document_version: int,
    markdown: str,
    index_schema_version: str = INDEX_SCHEMA_VERSION,
) -> str:
    """在结构解析前确定 revision，使所有派生身份使用同一命名空间。

    与 ``create_content_revision`` 的差异：本函数只生成 revision ID，
    不需要 ``DocumentStructure``，因此可以在结构解析之前就被调用，
    用于派生 Section ID 等下游身份。

    身份由四个维度共同决定：
    - resource_id：归属哪个资源。
    - document_version：上游文档版本。
    - content_hash：原文 sha256，内容变化即失效。
    - index_schema_version：索引规则版本，schema 变更即失效。
    """
    if not resource_id:
        raise ValueError("resource_id must not be empty")
    if document_version < 1:
        raise ValueError("document_version must be positive")
    if not index_schema_version:
        raise ValueError("index_schema_version must not be empty")

    content_hash = sha256(markdown.encode("utf-8")).hexdigest()
    # 使用 \0 作为分隔符避免四元组拼接产生歧义（\0 不会出现在正常字符串中）。
    identity = "\0".join(
        (resource_id, str(document_version), content_hash, index_schema_version)
    )
    return f"rrev_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
