"""知识图谱 Mention 反查仓储契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.models.acl import PermissionScope
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import KnowledgeNode


class MentionLookup(Protocol):
    """从已核验 SourceRef 发现当前已发布图中的节点。"""

    async def find_nodes(
        self,
        *,
        evidence: Sequence[EvidenceRecord],
        permission_scope: PermissionScope,
        limit: int,
    ) -> list[KnowledgeNode]: ...
