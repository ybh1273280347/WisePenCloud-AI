from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from chat.core.persistence.redis._utils.jsonable import to_jsonable
from chat.core.persistence._utils.payload_readers import (
    read_optional_datetime,
    read_optional_int,
    read_optional_str,
    read_optional_trimmed_str,
    read_trimmed_str_sequence,
)


class _SampleMode(StrEnum):
    ACTIVE = "active"


class _FallbackObject:
    def __str__(self) -> str:
        return "fallback"


def test_to_jsonable_recursively_converts_redis_payload_values() -> None:
    timestamp = datetime(2026, 7, 5, 10, 30, tzinfo=timezone.utc)

    assert to_jsonable(
        {
            1: {
                "items": (_SampleMode.ACTIVE, timestamp, _FallbackObject()),
            },
        }
    ) == {
        "1": {
            "items": [
                "active",
                "2026-07-05T10:30:00+00:00",
                "fallback",
            ],
        },
    }


def test_payload_readers_decode_optional_redis_values() -> None:
    timestamp = datetime(2026, 7, 5, 10, 30, tzinfo=timezone.utc)

    assert read_optional_str("") == ""
    assert read_optional_trimmed_str("  title  ") == "title"
    assert read_optional_trimmed_str("  ") is None
    assert read_optional_int("12") == 12
    assert read_optional_datetime(timestamp.isoformat()) == timestamp
    assert read_trimmed_str_sequence([" a ", "", 3, None]) == ("a", "3", "None")
    assert read_trimmed_str_sequence("abc") == ()
