"""候选召回能力的领域 port。"""

from typing import Protocol

from rag.domain.retrieval import CandidateSearchRequest, RetrievalCandidate


class CandidateSearch(Protocol):
    """按查询事实返回尚未排序和核验的检索候选。"""

    async def search(
        self,
        request: CandidateSearchRequest,
    ) -> list[RetrievalCandidate]: ...
