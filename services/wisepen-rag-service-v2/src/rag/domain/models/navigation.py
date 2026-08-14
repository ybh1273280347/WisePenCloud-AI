"""LOCATE、READ、EXPAND 共享的导航状态事实。"""

from dataclasses import dataclass, field


class NavigationStateNotFoundError(RuntimeError):
    """导航状态不存在、已过期或不属于当前用户会话。"""


@dataclass(slots=True)
class NavigationState:
    """绑定用户和会话的短生命周期导航状态。"""

    state_id: str
    user_id: str
    session_id: str
    known_node_ids: list[str] = field(default_factory=list)
