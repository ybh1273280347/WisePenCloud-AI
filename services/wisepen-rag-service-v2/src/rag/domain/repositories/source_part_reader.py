"""权威原文分片读取契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.content_revision import SourcePart
from rag.utils.chunkers import SourceSpan


class SourcePartReader(Protocol):
    """读取指定 revision 的完整或局部 SourcePart。"""

    async def get_parts(
        self,
        content_revision: str,
        source_spans: Sequence[SourceSpan] | None = None,
    ) -> list[SourcePart]: ...
