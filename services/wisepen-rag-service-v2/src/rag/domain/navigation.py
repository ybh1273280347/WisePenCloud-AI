"""LOCATE、READ、EXPAND 共享的导航状态事实。"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class KnownSection:
    """导航状态中已经发现的 Section 及发现时的资源 revision。"""

    resource_id: str
    content_revision: str


@dataclass(slots=True)
class NavigationState:
    """绑定用户和会话的短生命周期导航状态。"""

    state_id: str
    user_id: str
    session_id: str
    root_query: str
    known_sections: dict[str, KnownSection] = field(default_factory=dict)
    known_node_ids: list[str] = field(default_factory=list)
