"""基于 HTTP 响应头与 hishel RFC 9111 逻辑的缓存过期时间计算。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from hishel._core._headers import Headers, parse_cache_control
from hishel._core._spec import get_freshness_lifetime
from hishel._core.models import Response

_DEFAULT_TTL = timedelta(seconds=7200)
_MAX_TTL = timedelta(seconds=86400)


@dataclass(frozen=True, slots=True)
class CacheTTL:
    """智能计算出的缓存过期时间。"""

    expire_at: datetime
    no_store: bool = False  # 当响应头含 no-store 时为 True


def compute_ttl(
        *,
        headers: dict[str, str],
        now: datetime,
        is_shared_cache: bool = False,
        status_code: int = 200,
) -> CacheTTL:
    """从 HTTP 响应头计算缓存过期时间。

    Parameters
    ----------
    headers:
        HTTP 响应头字典（小写 key）。
    now:
        当前 UTC 时间。
    is_shared_cache:
        当前缓存是否为共享缓存（PUBLIC 域）。为 True 时会优先使用 s-maxage。
    status_code:
        HTTP 状态码，用于启发式缓存判断。

    Returns
    -------
    CacheTTL
        含 expire_at / no_store 的计算结果。
    """
    cc = parse_cache_control(headers.get("cache-control"))

    # no-store：不缓存，调用方应跳过写缓存
    if cc.no_store:
        return CacheTTL(
            expire_at=now,
            no_store=True,
        )

    # 利用 hishel 的 RFC 9111 新鲜度计算
    hishel_response = Response(
        status_code=status_code,
        headers=Headers(headers),
    )
    freshness_seconds = get_freshness_lifetime(hishel_response, is_shared_cache)

    ttl = (
        timedelta(seconds=freshness_seconds)
        if freshness_seconds is not None and freshness_seconds >= 0
        else _DEFAULT_TTL
    )

    # must-revalidate / no-cache / max-age=0：没有再验证能力时视为立即过期
    if cc.must_revalidate or cc.no_cache is True or (
            cc.max_age is not None and cc.max_age == 0
    ):
        ttl = timedelta(0)

    return CacheTTL(
        expire_at=now + min(ttl, _MAX_TTL),
        no_store=False,
    )
