from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from chat.application.tools.web_tools.search_services.providers.models import SearchProviderName
from chat.application.tools.web_tools.search_services.searchers import ProviderSearcher
from .hydrators import (
    OpenAlexFailureReason,
    PaperHydrator,
)
from .result_builder import (
    AcademicHydrationOutcome,
)
from ..candidates import WebSearchCandidate
from ..search import WebSearchCustomSource, WebSearchResult, execute_provider_search


class AcademicSearchService:
    """学术搜索 service：负责单次 academic provider 调用与 OpenAlex 水合。"""

    __slots__ = ("_paper_hydrator", "_platform_searchers")

    def __init__(
        self,
        *,
        platform_searchers: Mapping[SearchProviderName, ProviderSearcher],
        paper_hydrator: PaperHydrator,
    ) -> None:
        self._platform_searchers = dict(platform_searchers)
        self._paper_hydrator = paper_hydrator

    async def search(
        self,
        *,
        query: str,
        max_results: int = 10,
        custom_source: WebSearchCustomSource | None = None,
        platform_provider: SearchProviderName = SearchProviderName.FOUGET_DDG,
    ) -> WebSearchResult:
        return await execute_provider_search(
            query=query,
            custom_source=custom_source,
            platform_provider=platform_provider,
            platform_searchers=self._platform_searchers,
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
        """按既定边界对候选做 OpenAlex 水合，并保留 Exa 兜底 URL。"""
        outcomes: list[AcademicHydrationOutcome] = []
        quota_available = True

        for candidate in candidates:
            if not openalex_api_key or not quota_available:
                outcomes.append(
                    AcademicHydrationOutcome(
                        candidate=candidate,
                        final_url_source="exa",
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
                        final_url_source="exa",
                    )
                )
                continue

            if hydrated.failure_reason is not None:
                outcomes.append(
                    AcademicHydrationOutcome(
                        candidate=candidate,
                        final_url_source="exa",
                    )
                )
                continue

            final_url = candidate.url
            final_url_source = "exa"
            oa_url = hydrated.open_access.oa_url if hydrated.open_access else None
            if oa_url and oa_url.startswith(("http://", "https://")):
                final_url = oa_url
                final_url_source = "openalex"

            outcomes.append(
                AcademicHydrationOutcome(
                    candidate=replace(candidate, url=final_url),
                    final_url_source=final_url_source,
                    doi=hydrated.doi,
                    publication_year=hydrated.publication_year,
                    cited_by_count=hydrated.cited_by_count,
                    authors=hydrated.authors,
                    institutions=hydrated.institutions,
                    open_access=hydrated.open_access,
                )
            )

        return tuple(outcomes)
