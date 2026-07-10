from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Sequence
from urllib.parse import urlsplit

import dns.message
import dns.query
import dns.rdatatype

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UrlSecurityError(ValueError):
    pass


_ALLOWED_PORTS = frozenset({80, 443})
_CONTROL_OR_SPACE_RE = re.compile(r"[\s\x00-\x1f\x7f]")

# 显式列出敏感和非公网网段，避免依赖不同 Python 版本的 ipaddress 分类差异。
_BLOCKED_IP_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b::/96",
        "100::/64",
        "2001::/23",
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)

# 某些受污染网络可能将任意域名解析到基准测试网段。
_FAKE_IP_NETWORKS = (
    ipaddress.ip_network("198.18.0.0/15"),
)

_DOH_SERVERS: tuple[str, ...] = (
    "https://dns.alidns.com/dns-query",
    "https://doh.pub/dns-query",
    "https://doh.360.cn/dns-query",
)


def validate_public_http_url(
        url: str,
        *,
        doh_servers: Sequence[str] = _DOH_SERVERS,
) -> str:
    """校验 URL 是否可作为公网 HTTP(S) 请求目标。"""
    if not url:
        raise UrlSecurityError("URL is empty")

    if url != url.strip() or _CONTROL_OR_SPACE_RE.search(url):
        raise UrlSecurityError(
            "URL contains whitespace or control characters"
        )

    # 禁止反斜杠，避免 urllib、浏览器和 HTTP 客户端产生解析差异。
    if "\\" in url:
        raise UrlSecurityError("URL cannot contain backslashes")

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UrlSecurityError("URL is malformed") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise UrlSecurityError("URL scheme must be http or https")

    if not parsed.netloc or not hostname:
        raise UrlSecurityError("URL is missing a hostname")

    if parsed.username is not None or parsed.password is not None:
        raise UrlSecurityError("URL cannot contain userinfo")

    if port is not None and port not in _ALLOWED_PORTS:
        raise UrlSecurityError("URL port is not allowed")

    _resolve_public_host_ips(
        hostname,
        doh_servers=doh_servers,
    )
    return url


async def validate_public_http_url_async(
        url: str,
        *,
        doh_servers: Sequence[str] = _DOH_SERVERS,
) -> str:
    """在线程池中执行包含同步 DNS 查询的 URL 安全校验。"""
    return await asyncio.to_thread(
        validate_public_http_url,
        url,
        doh_servers=doh_servers,
    )


def _resolve_public_host_ips(
        hostname: str,
        *,
        doh_servers: Sequence[str],
) -> tuple[str, ...]:
    normalized = hostname.rstrip(".").lower()
    if not normalized:
        raise UrlSecurityError("URL is missing a hostname")

    if normalized == "localhost" or normalized.endswith(".local"):
        raise UrlSecurityError("Hostname is blocked")

    # IPv6 zone ID 可指定本地网卡，不允许出现在公网抓取目标中。
    if "%" in normalized:
        raise UrlSecurityError("Hostname cannot contain an IPv6 zone ID")

    try:
        literal_ip = ipaddress.ip_address(normalized)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        _reject_blocked_ip(literal_ip)
        return (str(literal_ip),)

    try:
        # 统一转换为 ASCII IDNA 域名后再交给系统 DNS。
        normalized = normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlSecurityError("Hostname is invalid") from exc

    try:
        addr_infos = socket.getaddrinfo(
            normalized,
            None,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise UrlSecurityError(
            f"Hostname cannot be resolved: {normalized}"
        ) from exc

    try:
        ips = {
            ipaddress.ip_address(info[4][0])
            for info in addr_infos
        }
    except ValueError as exc:
        raise UrlSecurityError(
            f"Hostname returned an invalid address: {normalized}"
        ) from exc

    if not ips:
        raise UrlSecurityError(
            f"Hostname did not resolve to any address: {normalized}"
        )

    # 系统 DNS 全部返回疑似污染地址时，再使用可信 DoH 重试。
    if all(
            any(ip in network for network in _FAKE_IP_NETWORKS)
            for ip in ips
    ):
        ips = set(
            _resolve_with_doh(
                normalized,
                doh_servers=doh_servers,
            )
        )
        if not ips:
            raise UrlSecurityError(
                "Hostname resolved to fake IP and DoH could not resolve "
                f"a real address: {normalized}"
            )

    for ip in ips:
        _reject_blocked_ip(ip)

    return tuple(
        str(ip)
        for ip in sorted(
            ips,
            key=lambda value: (value.version, int(value)),
        )
    )


def _resolve_with_doh(
        hostname: str,
        *,
        doh_servers: Sequence[str],
) -> tuple[IPAddress, ...]:
    for doh_url in doh_servers:
        resolved: set[IPAddress] = set()

        # 同时查询 IPv4 和 IPv6；单个查询失败不影响其他服务。
        for record_type in (
                dns.rdatatype.A,
                dns.rdatatype.AAAA,
        ):
            try:
                query = dns.message.make_query(
                    hostname,
                    record_type,
                )
                response = dns.query.https(
                    query,
                    doh_url,
                    timeout=5.0,
                )
            except Exception:
                continue

            for rrset in response.answer:
                for item in rrset:
                    try:
                        resolved.add(ipaddress.ip_address(str(item)))
                    except ValueError:
                        # CNAME 等非 IP 记录不参与安全判断。
                        continue

        if resolved:
            return tuple(
                sorted(
                    resolved,
                    key=lambda value: (value.version, int(value)),
                )
            )

    return ()


def _reject_blocked_ip(ip: IPAddress) -> None:
    if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or any(ip in network for network in _BLOCKED_IP_NETWORKS)
    ):
        raise UrlSecurityError(
            f"Hostname resolves to a blocked IP address: {ip}"
        )
