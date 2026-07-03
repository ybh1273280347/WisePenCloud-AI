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
) -> ToolReturn:
    """组装 web_search 的可见返回。

    - candidates：完整候选列表。
    - supplier_answers：供应商对 query 的直答（去重），仅作为检索提示。
    - recommended_ids：按优先级排序的候选编号，1 到 5 个。
    """
    supplier_answers = tuple(dict.fromkeys(r.answer for r in responses if r.answer))

    suggested_action = SuggestedAction(
        tool_name="web_fetch",
        reason=(
            "Use supplier answers and candidate summaries as retrieval hints. "
            "If those summaries fully answer the question, web_fetch is optional; "
            "fetch selected search refs when you need stronger evidence, details, or verification."
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
    if supplier_answers:
        visible_result["supplier_answers"] = supplier_answers

    return ToolReturn(
        tag="web_search_result",
        visible_result=visible_result,
        cacheable_texts=(),  # 明确不缓存
    )
