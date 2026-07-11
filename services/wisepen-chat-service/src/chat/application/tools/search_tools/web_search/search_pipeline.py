from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.search_tools.web_search.core.errors import WebSearchEmptyResult
from chat.application.tools.search_tools.web_search.core.sources import WebSearchRuntimeSource
from chat.application.tools.search_tools.web_search.pipeline.candidate_selector import (
    select_recommended_ids,
)
from chat.application.tools.search_tools.web_search.pipeline.candidates_builder import (
    WebSearchCandidate,
    build_candidates,
)
from chat.application.tools.search_tools.web_search.pipeline.search_executor import (
    WebSearchResult,
    execute_provider_search,
)
from chat.application.tools.search_tools.web_search.providers.models import SearchMode

MAX_RECOMMENDED_CANDIDATES = 5
FALLBACK_CANDIDATES_COUNT = 3


@dataclass(frozen=True, slots=True)
class SearchPipelineResult:
    search_result: WebSearchResult
    candidates: tuple[WebSearchCandidate, ...]
    recommended_ids: tuple[str, ...]


class SearchPipeline:
    """执行搜索、候选构建与推荐选择的完整管线。"""

    async def search(
            self,
            *,
            query: str,
            max_results: int,
            source: WebSearchRuntimeSource,
            mode: SearchMode,
    ) -> SearchPipelineResult:
        async def search_once(searcher):
            search = searcher.search_academic if mode == SearchMode.ACADEMIC else searcher.search_web
            return await search(
                query=query,
                max_results=max_results,
            )

        result = await execute_provider_search(
            query=query,
            source=source,
            search_once=search_once,
        )
        candidates = build_candidates(result.responses)
        if not candidates:
            raise WebSearchEmptyResult(provider=source.provider, reason="搜索没有返回结果")

        recommended_ids = await select_recommended_ids(
            search_query=query,
            candidates=candidates,
            max_recommended_candidates=MAX_RECOMMENDED_CANDIDATES,
            fallback_candidates_count=FALLBACK_CANDIDATES_COUNT,
        )
        return SearchPipelineResult(
            search_result=result,
            candidates=candidates,
            recommended_ids=recommended_ids,
        )
