from __future__ import annotations

from chat.application.tools.web_tools.search_services.sources import WebSearchRuntimeSource
from chat.application.tools.web_tools.search_services.services.academic_search.hydrators import (
    OpenAlexFailureReason,
    PaperHydrator,
)
from chat.application.tools.web_tools.search_services.services.academic_search.result_builder import (
    AcademicHydrationOutcome,
)
from chat.application.tools.web_tools.search_services.services.candidates_builder import WebSearchCandidate
from chat.application.tools.web_tools.search_services.services.search_executor import (
    WebSearchResult,
    execute_provider_search,
)


class AcademicSearchService:
    """学术搜索 service：负责单次 academic provider 调用与 OpenAlex 水合。"""

    __slots__ = ("_paper_hydrator",)

    def __init__(
            self,
            *,
            paper_hydrator: PaperHydrator,
    ) -> None:
        self._paper_hydrator = paper_hydrator

    async def search(
            self,
            *,
            query: str,
            max_results: int = 10,
            source: WebSearchRuntimeSource,
    ) -> WebSearchResult:
        return await execute_provider_search(
            query=query,
            source=source,
            search_once=lambda searcher: searcher.search_academic(
                query=query,
                max_results=max_results,
            ),
        )

    async def hydrate_candidates(
            self,
            *,
            candidates: tuple[WebSearchCandidate, ...],
            openalex_api_key: str | None,
    ) -> tuple[AcademicHydrationOutcome, ...]:
        """按既定边界对候选做 OpenAlex 水合，抓取 URL 始终保留搜索源结果。"""
        outcomes: list[AcademicHydrationOutcome] = []
        quota_available = True

        for candidate in candidates:
            if not openalex_api_key or not quota_available:
                outcomes.append(
                    AcademicHydrationOutcome(
                        candidate=candidate,
                    )
                )
                continue

            hydrated = await self._paper_hydrator.hydrate(
                api_key=openalex_api_key,
                url=candidate.url,
                title=candidate.title,
            )
            if hydrated.failure_reason == OpenAlexFailureReason.RATE_LIMITED:
                quota_available = False
                outcomes.append(
                    AcademicHydrationOutcome(
                        candidate=candidate,
                    )
                )
                continue

            if hydrated.failure_reason is not None:
                outcomes.append(
                    AcademicHydrationOutcome(
                        candidate=candidate,
                    )
                )
                continue

            outcomes.append(
                AcademicHydrationOutcome(
                    candidate=candidate,
                    doi=hydrated.doi,
                    publication_year=hydrated.publication_year,
                    cited_by_count=hydrated.cited_by_count,
                    authors=hydrated.authors,
                    institutions=hydrated.institutions,
                )
            )

        return tuple(outcomes)
