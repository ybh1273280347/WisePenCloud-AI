from __future__ import annotations

from typing import Any

from qdrant_client import models as qdrant_models

from ..models import RagPermissionScope


class RagPermissionFilterBuilder:
    """为 RAG 检索后端生成权限前置过滤条件。"""

    def build_elastic_filter(self, scope: RagPermissionScope) -> dict[str, Any]:
        should = [
            {"term": {"owner_id": scope.user_id}},
            {"term": {"readable_users": scope.user_id}},
        ]

        if scope.managed_group_ids:
            should.append(
                self._nested_group_acl_filter(
                    [
                        {"terms": {"computed_group_acls.group_id": list(scope.managed_group_ids)}},
                    ]
                )
            )

        if scope.joined_group_ids:
            should.append(
                self._nested_group_acl_filter(
                    [
                        {"terms": {"computed_group_acls.group_id": list(scope.joined_group_ids)}},
                        {"term": {"computed_group_acls.is_readable": True}},
                    ],
                    must_not=[
                        {"term": {"computed_group_acls.excluded_read_users": scope.user_id}},
                    ],
                )
            )
            should.append(
                self._nested_group_acl_filter(
                    [
                        {"terms": {"computed_group_acls.group_id": list(scope.joined_group_ids)}},
                        {"term": {"computed_group_acls.is_readable": False}},
                        {"term": {"computed_group_acls.readable_users": scope.user_id}},
                    ]
                )
            )

        return {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
            }
        }

    def build_qdrant_filter(self, scope: RagPermissionScope) -> qdrant_models.Filter:
        should: list[qdrant_models.Condition] = [
            qdrant_models.FieldCondition(
                key="owner_id",
                match=qdrant_models.MatchValue(value=scope.user_id),
            ),
            qdrant_models.FieldCondition(
                key="readable_users",
                match=qdrant_models.MatchValue(value=scope.user_id),
            ),
        ]

        if scope.managed_group_ids:
            should.append(
                self._nested_qdrant_group_acl_filter(
                    [
                        qdrant_models.FieldCondition(
                            key="group_id",
                            match=qdrant_models.MatchAny(any=list(scope.managed_group_ids)),
                        ),
                    ]
                )
            )

        if scope.joined_group_ids:
            should.append(
                self._nested_qdrant_group_acl_filter(
                    [
                        qdrant_models.FieldCondition(
                            key="group_id",
                            match=qdrant_models.MatchAny(any=list(scope.joined_group_ids)),
                        ),
                        qdrant_models.FieldCondition(
                            key="is_readable",
                            match=qdrant_models.MatchValue(value=True),
                        ),
                    ],
                    must_not=[
                        qdrant_models.FieldCondition(
                            key="excluded_read_users",
                            match=qdrant_models.MatchValue(value=scope.user_id),
                        ),
                    ],
                )
            )
            should.append(
                self._nested_qdrant_group_acl_filter(
                    [
                        qdrant_models.FieldCondition(
                            key="group_id",
                            match=qdrant_models.MatchAny(any=list(scope.joined_group_ids)),
                        ),
                        qdrant_models.FieldCondition(
                            key="is_readable",
                            match=qdrant_models.MatchValue(value=False),
                        ),
                        qdrant_models.FieldCondition(
                            key="readable_users",
                            match=qdrant_models.MatchValue(value=scope.user_id),
                        ),
                    ]
                )
            )

        return qdrant_models.Filter(should=should)

    def _nested_group_acl_filter(
            self,
            filter_clauses: list[dict[str, Any]],
            *,
            must_not: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        bool_query: dict[str, Any] = {
            "filter": filter_clauses,
        }
        if must_not:
            bool_query["must_not"] = must_not

        return {
            "nested": {
                "path": "computed_group_acls",
                "query": {
                    "bool": bool_query,
                },
            }
        }

    def _nested_qdrant_group_acl_filter(
            self,
            filter_clauses: list[qdrant_models.Condition],
            *,
            must_not: list[qdrant_models.Condition] | None = None,
    ) -> qdrant_models.NestedCondition:
        return qdrant_models.NestedCondition(
            nested=qdrant_models.Nested(
                key="computed_group_acls",
                filter=qdrant_models.Filter(
                    must=filter_clauses,
                    must_not=must_not,
                ),
            )
        )
