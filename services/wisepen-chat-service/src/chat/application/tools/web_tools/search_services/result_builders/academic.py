from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.web_tools.search_services.hydrators.academic import HydratedPaperAuthor
from chat.application.tools.web_tools.search_services.pipeline.candidates_builder import WebSearchCandidate


@dataclass(frozen=True, slots=True)
class VisibleAcademicAuthor:
    name: str
    institutions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VisibleAcademicSearchCandidate:
    search_ref: str
    title: str
    overview: str | None = None
    highlights: tuple[str, ...] = ()
    doi: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    authors: tuple[VisibleAcademicAuthor, ...] = ()
    institutions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcademicHydrationOutcome:
    candidate: WebSearchCandidate
    doi: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    authors: tuple[HydratedPaperAuthor, ...] = ()
    institutions: tuple[str, ...] = ()


def build_academic_search_tool_return(
        *,
        query: str,
        outcomes: tuple[AcademicHydrationOutcome, ...],
        recommended_ids: tuple[str, ...],
) -> ToolReturn:
    return ToolReturn(
        tag="academic_search_result",
        visible_result={
            "query": query,
            "candidates": tuple(
                VisibleAcademicSearchCandidate(
                    search_ref=outcome.candidate.search_ref,
                    title=outcome.candidate.title,
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
                )
                for outcome in outcomes
            ),
            "recommended_ids": recommended_ids,
        },
        cacheable_texts=(),
    )
