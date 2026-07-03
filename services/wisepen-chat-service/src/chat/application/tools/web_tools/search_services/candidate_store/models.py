from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebSearchCandidateMapping:
    """web_search 候选项到真实 URL 的短期映射。"""

    user_id: str
    search_ref: str
    url: str
    source_scope: str
