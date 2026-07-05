from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from chat.core.persistence.redis._utils import to_jsonable


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
