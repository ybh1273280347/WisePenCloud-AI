"""verify 能力读取 applied 权威证据的仓储契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.evidence import EvidenceRecord


class EvidenceReader(Protocol):
    async def read_applied_evidence(
        self,
        resource_id: str,
        content_revision: str,
        source_ref_ids: Sequence[str],
    ) -> dict[str, EvidenceRecord] | None: ...
