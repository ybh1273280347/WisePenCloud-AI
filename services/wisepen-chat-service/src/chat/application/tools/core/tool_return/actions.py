from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SuggestedActionPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

# 单个 Action 独立使用时的提示文案，与 SuggestedActions.notice 保持一致
_STANDALONE_NOTICE = (
    "Suggested actions are optional hints. They identify tools and route-level "
    "modes that may help, but they are not mandatory instructions or complete "
    "tool-call arguments."
)


@dataclass(slots=True)
class SuggestedAction:
    tool_name: str
    reason: str
    mode: str | None = None
    priority: SuggestedActionPriority = SuggestedActionPriority.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)
    # 独立使用时显示提示；被 SuggestedActions 包裹时由 __post_init__ 置 None，
    # 经 _normalize 过滤后不会出现在渲染输出中
    notice: str | None = field(default=_STANDALONE_NOTICE)


@dataclass(slots=True)
class SuggestedActions:
    suggested_actions: tuple[SuggestedAction, ...] = ()
    notice: str = _STANDALONE_NOTICE

    def __post_init__(self) -> None:
        # 被 SuggestedActions 包裹的子 Action 不再单独显示 notice，
        # 置 None 后 _normalize 会自动过滤，不会出现在渲染输出中
        for action in self.suggested_actions:
            action.notice = None
