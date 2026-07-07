from __future__ import annotations

from collections.abc import Sequence


def read_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(
        text
        for item in value
        if (text := str(item).strip())
    )


def permission_scope_key(group_role_map: dict[str, str]) -> str:
    return "|".join(
        f"{group_id}:{role}"
        for group_id, role in sorted(group_role_map.items())
    )
