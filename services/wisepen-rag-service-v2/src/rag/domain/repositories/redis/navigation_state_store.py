"""导航状态持久化 port。"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from rag.domain.models.navigation import KnownSection, NavigationState


class NavigationStateStore(Protocol):
    """创建、读取并原子扩展导航状态。"""

    async def create(
        self,
        *,
        user_id: str,
        session_id: str,
        root_query: str,
        known_sections: Mapping[str, KnownSection],
        known_node_ids: Sequence[str],
    ) -> NavigationState: ...

    async def get(self, state_id: str) -> NavigationState | None: ...

    async def add_known_sections(
        self,
        *,
        state_id: str,
        sections: Mapping[str, KnownSection],
    ) -> None: ...

    async def add_known_nodes(
        self,
        *,
        state_id: str,
        node_ids: Sequence[str],
    ) -> list[str]: ...
