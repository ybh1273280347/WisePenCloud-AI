from __future__ import annotations

from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.web_tools.search_services.pipeline.candidates_builder import (
    VisibleWebSearchCandidate,
    WebSearchCandidate,
)
from chat.application.tools.web_tools.search_services.pipeline.search_executor import (
    WebSearchResult,
)
from chat.application.tools.web_tools.search_services.providers.models import ProviderSearchResponse


def build_web_search_tool_return(
        result: WebSearchResult,
        *,
        candidates: tuple[WebSearchCandidate, ...],
        responses: tuple[ProviderSearchResponse, ...],
        recommended_ids: tuple[str, ...] = (),
) -> ToolReturn:
    """组装 web_search 的可见返回。

    - candidates：完整候选列表。
    - supplier_answers：供应商对 query 的直答（去重），仅作为检索提示。
    - recommended_ids：按优先级排序的候选编号，1 到 5 个。
    """
    supplier_answers = tuple(dict.fromkeys(r.answer for r in responses if r.answer))

    visible_result: dict[str, object] = {
        "query": result.query,
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
    }
    if supplier_answers:
        visible_result["supplier_answers"] = supplier_answers

    return ToolReturn(
        tag="web_search_result",
        visible_result=visible_result,
        cacheable_texts=(),  # 明确不缓存
    )
