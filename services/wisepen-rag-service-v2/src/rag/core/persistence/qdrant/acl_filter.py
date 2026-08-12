"""将 ACL 领域请求身份翻译为 Qdrant 查询条件。"""

from qdrant_client import models as qdrant_models

from rag.domain.models.acl import PermissionScope


def permission_filter(scope: PermissionScope) -> qdrant_models.Filter:
    """生成与 ResourceAcl.can_read 同语义的 Qdrant VIEW filter。"""
    user_id = scope.user_id
    should: list[qdrant_models.Condition] = [
        qdrant_models.FieldCondition(
            key="owner_id",
            match=qdrant_models.MatchValue(value=user_id),
        ),
        qdrant_models.FieldCondition(
            key="readable_users",
            match=qdrant_models.MatchValue(value=user_id),
        ),
    ]

    group_filters: list[qdrant_models.Condition] = []
    if scope.managed_group_ids:
        group_filters.append(
            _nested_group_filter(
                qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="group_id",
                            match=qdrant_models.MatchAny(
                                any=list(scope.managed_group_ids)
                            ),
                        )
                    ]
                )
            )
        )
    if scope.joined_group_ids:
        joined_ids = list(scope.joined_group_ids)
        group_filters.extend(
            [
                _nested_group_filter(
                    qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="group_id",
                                match=qdrant_models.MatchAny(any=joined_ids),
                            ),
                            qdrant_models.FieldCondition(
                                key="is_readable",
                                match=qdrant_models.MatchValue(value=True),
                            ),
                        ],
                        must_not=[
                            qdrant_models.FieldCondition(
                                key="excluded_read_users",
                                match=qdrant_models.MatchValue(value=user_id),
                            )
                        ],
                    )
                ),
                _nested_group_filter(
                    qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="group_id",
                                match=qdrant_models.MatchAny(any=joined_ids),
                            ),
                            qdrant_models.FieldCondition(
                                key="is_readable",
                                match=qdrant_models.MatchValue(value=False),
                            ),
                            qdrant_models.FieldCondition(
                                key="readable_users",
                                match=qdrant_models.MatchValue(value=user_id),
                            ),
                        ]
                    )
                ),
            ]
        )

    if group_filters:
        should.append(
            qdrant_models.Filter(
                must_not=[
                    qdrant_models.FieldCondition(
                        key="excluded_read_users",
                        match=qdrant_models.MatchValue(value=user_id),
                    )
                ],
                should=group_filters,
            )
        )
    return qdrant_models.Filter(should=should)


def _nested_group_filter(group_filter: qdrant_models.Filter) -> qdrant_models.NestedCondition:
    return qdrant_models.NestedCondition(
        nested=qdrant_models.Nested(key="group_acls", filter=group_filter)
    )
