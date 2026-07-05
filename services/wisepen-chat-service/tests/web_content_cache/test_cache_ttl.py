from __future__ import annotations

from datetime import datetime, timedelta, timezone

from chat.application.tools.common.web_content_cache.cache_ttl import compute_ttl


def test_compute_ttl_uses_default_expiration_without_cache_headers() -> None:
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

    ttl = compute_ttl(headers={}, now=now)

    assert ttl.no_store is False
    assert ttl.expire_at == now + timedelta(seconds=7200)


def test_compute_ttl_uses_http_freshness_when_available() -> None:
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

    ttl = compute_ttl(headers={"cache-control": "max-age=60"}, now=now)

    assert ttl.expire_at == now + timedelta(seconds=60)


def test_compute_ttl_caps_long_http_freshness() -> None:
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

    ttl = compute_ttl(headers={"cache-control": "max-age=999999"}, now=now)

    assert ttl.expire_at == now + timedelta(seconds=86400)


def test_compute_ttl_marks_no_store_without_expiration_window() -> None:
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

    ttl = compute_ttl(headers={"cache-control": "no-store"}, now=now)

    assert ttl.no_store is True
    assert ttl.expire_at == now


def test_compute_ttl_expires_no_cache_immediately() -> None:
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

    ttl = compute_ttl(headers={"cache-control": "no-cache"}, now=now)

    assert ttl.no_store is False
    assert ttl.expire_at == now
