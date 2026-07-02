from __future__ import annotations

import json

from chat.application.utils.llm_clients import QueryClient, build_query_client
from chat.core.config.app_settings import settings
from common.logger import info

CANDIDATE_RANKER_SYSTEM_PROMPT = """\
<instructions>
你是搜索结果排序器。给定"搜索查询"和"候选列表"（每项含编号、标题、URL、overview、highlights），按回答搜索查询的相关性和证据价值，输出候选编号的优先级排序。

<rules>
  - 只能从给定候选编号中选择，禁止编造编号。
  - 按相关性从高到低排序，最相关的放最前。
  - 最多返回 5 个编号；若候选不足 5 个，按实际数量返回。
</rules>

<invalid_examples>
  - 候选只有 [1]..[4]，返回 ["[1]","[5]","[99]"]  -> 错误：[5] 和 [99] 不在候选中。
  - 返回 ["1","2"]  -> 错误：编号必须带方括号，应为 ["[1]","[2]"]。
  - 返回 ["[1]","[1]","[2]"]  -> 错误：编号不能重复。
  - 返回 ["[2]","[1]"] 但未按相关性排序  -> 错误：必须最相关的在最前。
</invalid_examples>

<output_format>
只输出以下 JSON，不要添加任何前后缀或解释：
{
  "ranked_ids": ["[1]", "[2]", ...]
}
</output_format>
</instructions>"""


MAX_RANKED_CANDIDATES = 5


async def rank_candidate_ids(
    *,
    search_query: str,
    candidates_text: str,
    client: QueryClient | None = None,
) -> list[str]:
    """用小模型对候选编号按相关性排序，最多返回 MAX_RANKED_CANDIDATES 个编号。"""
    query_client = client or build_query_client(
        model=settings.QUERY_MODEL,
    )
    result = await query_client.aquery(
        prompt=(
            f"<search_query>{search_query.strip()}</search_query>\n"
            f"<candidates>{candidates_text.strip()}</candidates>"
        ),
        system_prompt=CANDIDATE_RANKER_SYSTEM_PROMPT,
        max_tokens=256,
    )
    info("ranker.rank_candidate_ids", search_query=search_query.strip()[:80], raw_response=result.content)
    try:
        payload = json.loads(result.content)
        if not isinstance(payload, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return []

    raw_ids = payload.get("ranked_ids")
    if not isinstance(raw_ids, list):
        return []

    ranked: list[str] = []
    for value in raw_ids:
        candidate_id = value.strip() if isinstance(value, str) else ""
        if candidate_id:
            ranked.append(candidate_id)
        if len(ranked) >= MAX_RANKED_CANDIDATES:
            break
    return ranked
