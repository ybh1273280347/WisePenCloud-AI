from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.core.tool_return import (
    SuggestedAction,
    SuggestedActionPriority,
    ToolReturn,
)
from .hydrators import HydratedPaperAuthor, HydratedPaperOpenAccess
from ..candidates import WebSearchCandidate


@dataclass(frozen=True, slots=True)
class VisibleAcademicAuthor:
    name: str
    institutions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VisibleAcademicOpenAccess:
    is_oa: bool | None = None
    oa_status: str | None = None
    oa_url: str | None = None


@dataclass(frozen=True, slots=True)
class VisibleAcademicSearchCandidate:
    search_ref: str
    title: str
    url: str
    final_url_source: str
    overview: str | None = None
    highlights: tuple[str, ...] = ()
    doi: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    authors: tuple[VisibleAcademicAuthor, ...] = ()
    institutions: tuple[str, ...] = ()
    open_access: VisibleAcademicOpenAccess | None = None


@dataclass(frozen=True, slots=True)
class AcademicHydrationOutcome:
    candidate: WebSearchCandidate
    final_url_source: str
    doi: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    authors: tuple[HydratedPaperAuthor, ...] = ()
    institutions: tuple[str, ...] = ()
    open_access: HydratedPaperOpenAccess | None = None


def build_academic_search_tool_return(
    *,
    question: str,
    final_query: str,
    outcomes: tuple[AcademicHydrationOutcome, ...],
    recommended_ids: tuple[str, ...],
) -> ToolReturn:
    return ToolReturn(
        tag="academic_search_result",
        visible_result={
            "query": question,
            "final_query": final_query,
            "candidates": tuple(
                VisibleAcademicSearchCandidate(
                    search_ref=outcome.candidate.search_ref,
                    title=outcome.candidate.title,
                    url=outcome.candidate.url,
                    final_url_source=outcome.final_url_source,
                    overview=outcome.candidate.overview,
                    highlights=outcome.candidate.highlights,
                    doi=outcome.doi,
                    publication_year=outcome.publication_year,
                    cited_by_count=outcome.cited_by_count,
                    authors=tuple(
                        VisibleAcademicAuthor(
                            name=author.name,
                            institutions=author.institutions,
                        )
                        for author in outcome.authors
                    ),
                    institutions=outcome.institutions,
                    open_access=(
                        None
                        if outcome.open_access is None
                        else VisibleAcademicOpenAccess(
                            is_oa=outcome.open_access.is_oa,
                            oa_status=outcome.open_access.oa_status,
                            oa_url=outcome.open_access.oa_url,
                        )
                    ),
                )
                for outcome in outcomes
            ),
            "recommended_ids": recommended_ids,
            "suggested_action": SuggestedAction(
                tool_name="web_fetch",
                mode="from_search_results",
                reason="Fetch selected academic search refs before using them as evidence.",
                priority=SuggestedActionPriority.HIGH,
            ),
        },
        cacheable_texts=(),
    )
