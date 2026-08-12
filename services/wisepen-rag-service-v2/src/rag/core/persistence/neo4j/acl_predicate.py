"""将 PermissionScope 翻译为 Neo4j ResourceNode ACL predicate。"""

from rag.domain.acl import PermissionScope


def acl_predicate(
    scope: PermissionScope,
    *,
    resource_alias: str,
) -> tuple[str, dict[str, object]]:
    """生成与 ResourceAcl.can_read 同语义的查询条件。"""
    return (
        f"""(
          {resource_alias}.owner_id = $acl_user_id
          OR $acl_user_id IN coalesce({resource_alias}.readable_users, [])
          OR (
            NOT $acl_user_id IN coalesce({resource_alias}.excluded_read_users, [])
            AND (
              EXISTS {{
                MATCH ({resource_alias})-[:RAG_V2_HAS_GROUP_ACL]->(managed:RagV2ResourceGroupAcl)
                WHERE managed.group_id IN $acl_managed_group_ids
              }}
              OR EXISTS {{
                MATCH ({resource_alias})-[:RAG_V2_HAS_GROUP_ACL]->(joined:RagV2ResourceGroupAcl)
                WHERE joined.group_id IN $acl_joined_group_ids
                  AND (
                    (joined.is_readable = true
                     AND NOT $acl_user_id IN coalesce(joined.excluded_read_users, []))
                    OR (joined.is_readable = false
                        AND $acl_user_id IN coalesce(joined.readable_users, []))
                  )
              }}
            )
          )
        )""",
        {
            "acl_user_id": scope.user_id,
            "acl_managed_group_ids": list(scope.managed_group_ids),
            "acl_joined_group_ids": list(scope.joined_group_ids),
        },
    )
