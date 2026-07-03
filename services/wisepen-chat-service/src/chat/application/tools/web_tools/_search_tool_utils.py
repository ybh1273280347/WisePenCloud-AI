from __future__ import annotations

from chat.application.tools.web_tools.search_services.candidate_store.repository import (
    WebSearchCandidateRepository,
)
from chat.application.tools.web_tools.search_services.ranking import rank_candidate_ids
from chat.application.tools.web_tools.search_services.services.candidates import (
    WebSearchCandidate,
    build_candidate_mappings,
)


async def select_recommended_ids(
    *,
    search_query: str,
    candidates: tuple[WebSearchCandidate, ...],
    max_recommended_candidates: int,
    fallback_candidates_count: int,
) -> tuple[str, ...]:
    if not candidates:
        return ()

    # 用小模型对候选结果排序，挑选最相关的推荐给模型
    ranked = await rank_candidate_ids(
        search_query=search_query,
        candidates_text=_candidates_text(candidates),
    )
    if ranked:
        valid_ids = {candidate.candidate_id for candidate in candidates}
        filtered = tuple(candidate_id for candidate_id in ranked if candidate_id in valid_ids)[
            :max_recommended_candidates
        ]
        if filtered:
            return filtered

    # 排序失败时的兜底策略：按原始顺序取前 N 条
    return tuple(candidate.candidate_id for candidate in candidates[:fallback_candidates_count])


async def store_candidate_mappings(
    *,
    repository: WebSearchCandidateRepository,
    ttl_seconds: int,
    user_id: str,
    candidates: tuple[WebSearchCandidate, ...],
) -> None:
    # 持久化 search_ref → URL 映射，供后续 web_fetch 溯源使用
    for mapping in build_candidate_mappings(candidates, user_id=user_id):
        await repository.set_mapping(mapping, ttl_seconds=ttl_seconds)


def _candidates_text(candidates: tuple[WebSearchCandidate, ...]) -> str:
    # 拼接候选摘要文本，供排序模型（ranker）消费
    lines: list[str] = []
    for candidate in candidates:
        parts = [
            f"id: {candidate.candidate_id}",
            f"title: {candidate.title}",
            f"url: {candidate.url}",
        ]
        if candidate.overview:
            parts.append(f"overview: {candidate.overview}")
        if candidate.highlights:
            parts.append("highlights: " + " | ".join(candidate.highlights))
        lines.append("\n".join(parts))
    return "\n\n".join(lines)
