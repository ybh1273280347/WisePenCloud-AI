"""导航状态领域事实到 Redis hash 字段的序列化。"""

import json
from collections.abc import Mapping

from rag.domain.navigation import KnownSection, NavigationState


def serialize_sections(
    sections: Mapping[str, KnownSection],
) -> dict[str, dict[str, str]]:
    return {
        section_id: {
            "resource_id": section.resource_id,
            "content_revision": section.content_revision,
        }
        for section_id, section in sections.items()
    }


def serialize_navigation_state(state: NavigationState) -> dict[str, str]:
    return {
        "user_id": state.user_id,
        "session_id": state.session_id,
        "root_query": state.root_query,
        "known_sections": json.dumps(
            serialize_sections(state.known_sections),
            ensure_ascii=False,
        ),
        "known_nodes": json.dumps(state.known_node_ids, ensure_ascii=False),
    }
