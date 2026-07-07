from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast


def read_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def read_optional_trimmed_str(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def read_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def read_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def read_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def read_trimmed_str_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(
        candidate
        for item in value
        if (candidate := str(item).strip())
    )
