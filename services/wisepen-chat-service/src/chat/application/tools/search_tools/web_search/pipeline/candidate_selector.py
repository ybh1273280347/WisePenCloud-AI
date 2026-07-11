from __future__ import annotations

import json

from chat.application.tools.search_tools.web_search.pipeline.candidates_builder import (
    WebSearchCandidate,
)
from chat.application.utils.llm_clients import QueryClient, build_query_client
from chat.application.utils.xml_markup import xml_attr, xml_cdata
from chat.core.config.app_settings import settings
from common.logger import info, warn

CANDIDATE_SELECTOR_SYSTEM_PROMPT = """\
# 角色

你是搜索候选选择器。

# 任务

根据 `search_query`，从候选结果中选择相关性和证据价值最高的候选编号，并按推荐优先级排序。

# 输入

运行期输入由若干 `<candidate>` 和最后一个 `<search_query>` 组成。

每个候选可能包含标题、URL、overview 和若干 highlight，`id` 是形如 `[1]` 的唯一编号。

# 规则

- `selected_ids` 只能包含输入中存在的原始 `candidate id`。
- 返回 0 到 5 个高质量编号，宁缺勿滥，不重复。
- 保持编号的 `[1]` 原始格式。

# 输出格式

仅输出严格 JSON 对象：

{"selected_ids":["[1]","[2]"]}
"""

MAX_SELECTED_CANDIDATES = 5


async def select_recommended_ids(
    *,
    search_query: str,
    candidates: tuple[WebSearchCandidate, ...],
    max_recommended_candidates: int,
    fallback_candidates_count: int,
) -> tuple[str, ...]:
    if not candidates:
        return ()

    selected = await _select_candidate_ids(
        search_query=search_query,
        candidates_xml=_candidates_xml(candidates),
    )
    if selected:
        valid_ids = {candidate.candidate_id for candidate in candidates}
        filtered = tuple(
            candidate_id
            for candidate_id in selected
            if candidate_id in valid_ids
        )[:max_recommended_candidates]
        if filtered:
            return filtered

    return tuple(
        candidate.candidate_id
        for candidate in candidates[:fallback_candidates_count]
    )


async def _select_candidate_ids(
    *,
    search_query: str,
    candidates_xml: str,
    client: QueryClient | None = None,
) -> list[str]:
    """用小模型选择最多 MAX_SELECTED_CANDIDATES 个候选编号。"""
    query_client = client or build_query_client(
        model=settings.QUERY_MODEL,
    )
    try:
        result = await query_client.aquery(
            prompt=_build_selector_prompt(
                search_query=search_query,
                candidates_xml=candidates_xml,
            ),
            system_prompt=CANDIDATE_SELECTOR_SYSTEM_PROMPT,
            max_tokens=1024,
        )
    except Exception as exc:
        # 候选选择仅优化推荐顺序，不能阻断已成功的 provider 搜索。
        warn(
            "search candidate selection skipped.",
            search_query=search_query.strip()[:80],
            reason=exc.__class__.__name__,
        )
        return []

    info(
        "selector.select_candidate_ids",
        search_query=search_query.strip()[:80],
        raw_response=result.content,
    )

    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, dict):
        return []

    raw_ids = payload.get("selected_ids")
    if not isinstance(raw_ids, list):
        return []

    selected: list[str] = []
    seen: set[str] = set()

    for value in raw_ids:
        candidate_id = value.strip() if isinstance(value, str) else ""
        if not candidate_id or candidate_id in seen:
            continue

        seen.add(candidate_id)
        selected.append(candidate_id)
        if len(selected) >= MAX_SELECTED_CANDIDATES:
            break

    return selected


def _build_selector_prompt(*, search_query: str, candidates_xml: str) -> str:
    """候选放在前面，将每次变化的查询放在输入末尾。"""
    return "\n".join(
        (
            candidates_xml.strip(),
            "",
            "<search_query>",
            xml_cdata(search_query.strip()),
            "</search_query>",
        )
    )


def _candidates_xml(candidates: tuple[WebSearchCandidate, ...]) -> str:
    blocks: list[str] = []

    for candidate in candidates:
        parts = [
            f'<candidate id="{xml_attr(candidate.candidate_id)}">',
            f"  <title>{xml_cdata(candidate.title)}</title>",
            f"  <url>{xml_cdata(candidate.url)}</url>",
        ]
        if candidate.overview:
            parts.append(
                f"  <overview>{xml_cdata(candidate.overview)}</overview>"
            )
        parts.extend(
            f"  <highlight>{xml_cdata(highlight)}</highlight>"
            for highlight in candidate.highlights
        )
        parts.append("</candidate>")
        blocks.append("\n".join(parts))

    return "\n".join(blocks)
