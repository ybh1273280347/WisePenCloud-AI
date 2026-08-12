"""Mongo 记录和实体到领域事实的反序列化。"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from rag.domain.acl import GroupResourceAcl, ResourceAcl
from rag.domain.content_revision import ContentRevision, SourcePart
from rag.domain.document_structure import PageRange, Section, StructureMode
from rag.domain.entities import (
    ContentRevisionEntity,
    GenerationCacheEntity,
    ReadingBlockEntity,
    ResourceAclEntity,
    SectionEntity,
    SourcePartEntity,
    SourceRefEntity,
)
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan


class AuthoritativeAclError(ValueError):
    """上游资源 ACL 数据不满足 RAG 所需契约。"""


def to_generation_cache_values(
    records: Sequence[GenerationCacheEntity],
) -> dict[str, str]:
    return {record.cache_key: record.payload for record in records}


def to_content_revision(record: ContentRevisionEntity) -> ContentRevision:
    return ContentRevision(
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        document_version=record.document_version,
        content_hash=record.content_hash,
        index_schema_version=record.index_schema_version,
        structure_mode=StructureMode(record.structure_mode),
        total_length=record.total_length,
        pages=[
            PageRange(
                page_index=page.page_index,
                page_label=page.page_label,
                source_span=SourceSpan(page.start_offset, page.end_offset),
            )
            for page in record.pages
        ],
    )


def to_source_part(record: SourcePartEntity) -> SourcePart:
    return SourcePart(
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        part_index=record.part_index,
        source_span=SourceSpan(record.start_offset, record.end_offset),
        text=record.text,
    )


def to_section(record: SectionEntity) -> Section:
    return Section(
        section_id=record.section_id,
        title=record.title,
        level=record.level,
        parent_section_id=record.parent_section_id,
        ordinal=record.ordinal,
        section_path=list(record.section_path),
        own_span=SourceSpan(record.own_start, record.own_end),
        subtree_span=SourceSpan(record.own_start, record.subtree_end),
        preview=record.preview,
    )


def to_reading_block(record: ReadingBlockEntity) -> ReadingBlock:
    return ReadingBlock(
        block_id=record.block_id,
        section_id=record.section_id,
        ordinal=record.ordinal,
        raw_text=record.raw_text,
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )


def to_source_ref(record: SourceRefEntity) -> SourceRef:
    return SourceRef(
        ref_id=record.ref_id,
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        chunk_id=record.chunk_id,
        reading_block_id=record.reading_block_id,
        section_id=record.section_id,
        section_path=list(record.section_path),
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )


def to_resource_acl(entity: ResourceAclEntity) -> ResourceAcl:
    return ResourceAcl(
        resource_id=entity.resource_id,
        acl_revision=entity.acl_revision,
        owner_id=entity.owner_id,
        readable_users=list(entity.readable_users),
        excluded_read_users=list(entity.excluded_read_users),
        group_acls=[
            GroupResourceAcl(
                group_id=group_acl.group_id,
                default_readable=group_acl.is_readable,
                readable_users=list(group_acl.readable_users),
                excluded_read_users=list(group_acl.excluded_read_users),
            )
            for group_acl in entity.group_acls
        ],
    )


def to_authoritative_resource_acl(
    record: dict[str, Any],
    resource_id: str,
) -> ResourceAcl:
    owner_id = record.get("ownerId")
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise AuthoritativeAclError("ownerId must be a non-empty string")

    update_time = record.get("updateTime")
    if not isinstance(update_time, datetime):
        raise AuthoritativeAclError("updateTime must be a datetime")
    if update_time.tzinfo is None:
        update_time = update_time.replace(tzinfo=UTC)

    user_access = _read_user_masks(record.get("specifiedUsersGrantedActionsMask"))
    return ResourceAcl(
        resource_id=resource_id,
        acl_revision=int(update_time.timestamp() * 1000),
        owner_id=owner_id.strip(),
        readable_users=user_access["readable_users"],
        excluded_read_users=user_access["excluded_read_users"],
        group_acls=_read_group_acls(record.get("computedGroupAcls")),
    )


def _read_user_masks(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {"readable_users": [], "excluded_read_users": []}

    readable_users: list[str] = []
    excluded_read_users: list[str] = []
    for user_id, mask in value.items():
        if not isinstance(user_id, str) or not user_id.strip():
            continue
        if isinstance(mask, bool) or not isinstance(mask, int):
            continue
        (readable_users if _has_view(mask) else excluded_read_users).append(
            user_id.strip()
        )
    return {
        "readable_users": readable_users,
        "excluded_read_users": excluded_read_users,
    }


def _read_group_acls(value: Any) -> list[GroupResourceAcl]:
    if not isinstance(value, dict):
        return []

    group_acls: list[GroupResourceAcl] = []
    for group_id, group_value in value.items():
        if not isinstance(group_id, str) or not group_id.strip():
            continue
        if not isinstance(group_value, dict):
            continue

        default_readable = _has_view(group_value.get("baseMask"))
        user_access = _read_user_masks(group_value.get("userMasks"))
        if default_readable:
            readable_users = []
            excluded_read_users = user_access["excluded_read_users"]
        else:
            readable_users = user_access["readable_users"]
            excluded_read_users = []
        group_acls.append(
            GroupResourceAcl(
                group_id=group_id.strip(),
                default_readable=default_readable,
                readable_users=readable_users,
                excluded_read_users=excluded_read_users,
            )
        )
    return group_acls


def _has_view(mask: Any) -> bool:
    return (
        isinstance(mask, int)
        and not isinstance(mask, bool)
        and (mask & (1 << 1)) != 0
    )
