from __future__ import annotations

import json

from chat.application.tools.search_tools.web_search.pipeline.candidates_builder import (
    WebSearchCandidate,
)
from chat.application.utils.llm_clients import QueryClient, build_query_client
from chat.application.utils.xml_markup import xml_attr, xml_cdata
from chat.core.config.app_settings import settings
from common.logger import info

CANDIDATE_SELECTOR_SYSTEM_PROMPT = """\
# 角色

你是搜索候选选择器。

# 任务

按搜索查询与候选内容的相关性和证据价值，选择最值得后续关注的候选编号。

# 输入

运行期输入是 XML：

- `<search_query>` 是用户的搜索查询。
- `<candidate>` 是候选结果，`id` 是唯一候选编号，例如 `[1]`。
- 候选内容可能包含标题、URL、overview 和 highlights。

# 规则

- 只能选择输入 XML 中存在的 `candidate id`，禁止编造编号。
- 编号必须保持 `[1]` 这种原始格式，不能改成 `1`。
- 每次返回 1 到 5 个高质量编号，宁缺勿滥，不要凑满 5 个。
- 如果没有足够相关的候选，只返回确信有帮助的编号。

# 输出格式

只输出一个 JSON 对象，结构为 `{"selected_ids":["[1]","[2]"]}`。

# 禁止

- 不要输出 Markdown 代码块、标题、列表或 JSON 外的任何文字。
- 不要解释选择理由、评分依据、筛选过程或候选内容。
- `selected_ids` 里不要重复同一个编号。
- `selected_ids` 里不要出现输入 XML 中不存在的 `candidate id`。
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
        filtered = tuple(candidate_id for candidate_id in selected if candidate_id in valid_ids)[
            :max_recommended_candidates
        ]
        if filtered:
            return filtered

    return tuple(candidate.candidate_id for candidate in candidates[:fallback_candidates_count])


async def _select_candidate_ids(
        *,
        search_query: str,
        candidates_xml: str,
        client: QueryClient | None = None,
) -> list[str]:
    """用小模型选择推荐候选编号，返回 1 到 MAX_SELECTED_CANDIDATES 个编号。"""
    query_client = client or build_query_client(
        model=settings.QUERY_MODEL,
    )
    result = await query_client.aquery(
        prompt=_build_selector_prompt(
            search_query=search_query,
            candidates_xml=candidates_xml,
        ),
        system_prompt=CANDIDATE_SELECTOR_SYSTEM_PROMPT,
        max_tokens=256,
    )
    info("selector.select_candidate_ids", search_query=search_query.strip()[:80], raw_response=result.content)
    try:
        payload = json.loads(result.content)
        if not isinstance(payload, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return []

    raw_ids = payload.get("selected_ids")
    if not isinstance(raw_ids, list):
        return []

    selected: list[str] = []
    for value in raw_ids:
        candidate_id = value.strip() if isinstance(value, str) else ""
        if candidate_id:
            selected.append(candidate_id)
        if len(selected) >= MAX_SELECTED_CANDIDATES:
            break
    return selected


def _build_selector_prompt(*, search_query: str, candidates_xml: str) -> str:
    return "\n".join(
        (
            "<candidate_selector_input>",
            f"  <search_query>{xml_cdata(search_query.strip())}</search_query>",
            "  <candidates>",
            candidates_xml.strip(),
            "  </candidates>",
            "</candidate_selector_input>",
        )
    )


def _candidates_xml(candidates: tuple[WebSearchCandidate, ...]) -> str:
    blocks: list[str] = []
    for candidate in candidates:
        parts = [
            f"    <candidate id=\"{xml_attr(candidate.candidate_id)}\">",
            f"      <title>{xml_cdata(candidate.title)}</title>",
            f"      <url>{xml_cdata(candidate.url)}</url>",
        ]
        if candidate.overview:
            parts.append(f"      <overview>{xml_cdata(candidate.overview)}</overview>")
        if candidate.highlights:
            parts.append("      <highlights>")
            parts.extend(
                f"        <highlight>{xml_cdata(highlight)}</highlight>"
                for highlight in candidate.highlights
            )
            parts.append("      </highlights>")
        parts.append("    </candidate>")
        blocks.append("\n".join(parts))
    return "\n".join(blocks)
