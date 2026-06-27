from __future__ import annotations

from typing import Any

from chat.application.tools.core.tool_return import (
    SuggestedAction,
    SuggestedActionPriority,
    ToolReturn,
)
from chat.application.tools.web_tools.search_services.providers.models import ProviderSearchResponse
from ..candidates import VisibleWebSearchCandidate, WebSearchCandidate


def build_web_search_tool_return(
    result: Any,
    *,
    candidates: tuple[WebSearchCandidate, ...],
    responses: tuple[ProviderSearchResponse, ...],
    display_query: str | None = None,
    recommended_ids: tuple[str, ...] = (),
    final_query: str = "",
) -> ToolReturn:
    """组装 web_search 的可见返回。

    - candidates：完整候选列表。
    - supplier_answers：供应商对 query 的直答（去重），仅作为检索提示。
    - final_query：最终生效的查询词（fallback 查询与原始查询不同时展示）。
    - recommended_ids：按优先级排序的候选编号，最多 5 个。
    """
    supplier_answers = tuple(dict.fromkeys(r.answer for r in responses if r.answer))

    suggested_action = SuggestedAction(
        tool_name="web_fetch",
        mode="from_search_results",
        reason=(
            "Fetch selected search refs before using them as evidence. "
            "supplier_answers are only retrieval hints and must not replace your own fetch and analysis."
        ),
        priority=SuggestedActionPriority.HIGH,
    )

    visible_result: dict[str, object] = {
        "query": display_query or result.query,
        "candidates": tuple(
            VisibleWebSearchCandidate(
                search_ref=candidate.search_ref,
                title=candidate.title,
                overview=candidate.overview,
                highlights=candidate.highlights,
            )
            for candidate in candidates
        ),
        "recommended_ids": recommended_ids,
        "suggested_action": suggested_action,
    }
    if final_query and final_query != (display_query or result.query):
        visible_result["final_query"] = final_query
    if supplier_answers:
        visible_result["supplier_answers"] = supplier_answers

    return ToolReturn(
        tag="web_search_result",
        visible_result=visible_result,
        cacheable_texts=(),  # 明确不缓存
    )
