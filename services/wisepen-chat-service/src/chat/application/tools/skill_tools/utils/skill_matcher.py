from abc import ABC, abstractmethod
from typing import List, Set, Optional

from chat.core.config.app_settings import settings
from chat.domain.entities.skill import SkillMeta
from chat.service_client import AIAssetClient
from common.logger import error


class SkillMatcher(ABC):
    """
    Skill 筛选器，返回当前请求可展示给 LLM 的 Skill 元信息
    """

    @abstractmethod
    async def match(
            self,
            on_demand_skill_ids: Set[str],
            user_query: str,
            skill_match_top_k: Optional[int] = None
    ) -> List[SkillMeta]: ...


class DefaultSkillMatcher(SkillMatcher):
    """
    默认 Skill 筛选器
    """

    def __init__(self, ai_asset_client: AIAssetClient) -> None:
        self._ai_asset_client = ai_asset_client

    async def match(
            self,
            on_demand_skill_ids: Set[str],
            user_query: str,
            skill_match_top_k: Optional[int] = None
    ) -> List[SkillMeta]:
        # 系统级内置 Skill 始终进入候选集，不受前端 on-demand 覆盖影响
        on_demand_skill_ids = set(on_demand_skill_ids or set()) | ALWAYS_AVAILABLE_BUILTIN_SKILL_IDS

        skill_meta_list: List[SkillMeta] = []
        try:
            skill_meta_list = await self._ai_asset_client.list_published_skills_meta(on_demand_skill_ids)
        except Exception as e:
            error("skill metadata resolve failed.", count=len(on_demand_skill_ids), e=e)

        top_k = max(1, skill_match_top_k or settings.SKILL_MATCH_TOP_K)
        return skill_meta_list[:top_k]
