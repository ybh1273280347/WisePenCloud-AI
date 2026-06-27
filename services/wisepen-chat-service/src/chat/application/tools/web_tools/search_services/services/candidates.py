from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat.application.tools.web_tools.search_services.candidate_store import WebSearchCandidateMapping
from chat.application.tools.web_tools.search_services.providers.models import ProviderSearchResponse
from chat.application.tools.web_tools.search_services.runtime_context import WebSearchMode, WebSearchRuntimeConfig


@dataclass(frozen=True, slots=True)
class WebSearchCandidate:
    search_ref: str
    search_run_id: str
    candidate_id: str  # [1] 形式的稳定候选编号，供后续模型引用
    source_id: str
    title: str
    url: str
    source_scope: str
    overview: str | None = None
    highlights: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VisibleWebSearchCandidate:
    search_ref: str
    title: str
    overview: str | None = None
    highlights: tuple[str, ...] = ()


def build_candidates(
    responses: tuple[ProviderSearchResponse, ...],
    *,
    search_config: WebSearchRuntimeConfig,
) -> tuple[WebSearchCandidate, ...]:
    """从 provider 响应构建候选列表，使用 [1]、[2] 形式的稳定编号。"""
    search_run_id = f"srch_{uuid.uuid4().hex[:16]}"
    return tuple(
        WebSearchCandidate(
            search_ref=f"r{uuid.uuid4().hex[:10]}",
            search_run_id=search_run_id,
            candidate_id=f"[{i}]",
            source_id=resp.source_id or search_config.source_id,
            title=item.title,
            url=item.url,
            source_scope="web_custom" if search_config.search_mode == WebSearchMode.CUSTOM else "web_public",
            overview=item.preview.overview,
            highlights=item.preview.highlights,
        )
        for i, (resp, item) in enumerate(
            ((resp, item) for resp in responses for item in resp.results),
            start=1,
        )
    )


def build_candidate_mappings(
    candidates: tuple[WebSearchCandidate, ...],
    *,
    user_id: str,
) -> tuple[WebSearchCandidateMapping, ...]:
    return tuple(
        WebSearchCandidateMapping(
            user_id=user_id,
            search_ref=candidate.search_ref,
            search_run_id=candidate.search_run_id,
            candidate_id=candidate.candidate_id,
            source_id=candidate.source_id,
            url=candidate.url,
            source_scope=candidate.source_scope,
            metadata={"title": candidate.title},
        )
        for candidate in candidates
    )
