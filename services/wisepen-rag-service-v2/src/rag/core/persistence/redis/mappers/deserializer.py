"""Redis hash 字段到导航状态领域事实的反序列化。"""

import json
from collections.abc import Mapping

from rag.domain.navigation import KnownSection, NavigationState


def deserialize_navigation_state(
    state_id: str,
    values: Mapping[object, object],
) -> NavigationState:
    sections_value = json.loads(_read_text(values, "known_sections"))
    nodes_value = json.loads(_read_text(values, "known_nodes"))
    if not isinstance(sections_value, dict) or not isinstance(nodes_value, list):
        raise TypeError(f"navigation state {state_id} has invalid collection fields")

    known_sections: dict[str, KnownSection] = {}
    for section_id, section in sections_value.items():
        if not isinstance(section_id, str) or not isinstance(section, dict):
            raise TypeError(f"navigation state {state_id} has invalid sections")
        known_sections[section_id] = KnownSection(
            resource_id=_required_text(section, "resource_id"),
            content_revision=_required_text(section, "content_revision"),
        )
    if not all(isinstance(node_id, str) for node_id in nodes_value):
        raise TypeError(f"navigation state {state_id} has invalid node IDs")
    return NavigationState(
        state_id=state_id,
        user_id=_read_text(values, "user_id"),
        session_id=_read_text(values, "session_id"),
        root_query=_read_text(values, "root_query"),
        known_sections=known_sections,
        known_node_ids=list(dict.fromkeys(nodes_value)),
    )


def _read_text(values: Mapping[object, object], field_name: str) -> str:
    value = values.get(field_name)
    if value is None:
        value = values.get(field_name.encode())
    if not isinstance(value, (str, bytes)):
        raise TypeError(f"navigation state field {field_name} is invalid")
    return value.decode() if isinstance(value, bytes) else value


def _required_text(value: Mapping[object, object], field_name: str) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value:
        raise TypeError(f"navigation section field {field_name} is invalid")
    return field_value
