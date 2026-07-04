from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Iterable, Sequence
from urllib.parse import urlparse

import dns.message
import dns.query
import dns.rdatatype


class UrlSecurityError(ValueError):
    pass


# 仅允许常见的 HTTP / HTTPS 端口，避免访问内网服务或非常规端口
_ALLOWED_PORTS = {80, 443}

# 需要阻断的 IP 网段，包括内网、回环、本地链路、保留地址、组播地址等
_BLOCKED_IP_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "198.18.0.0/15",
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

# 匹配空白字符和控制字符，防止 URL 中混入换行、空格、不可见字符等
_CONTROL_OR_SPACE_RE = re.compile(r"[\s\x00-\x1f\x7f]")

# 某些网络环境下，DNS 污染或拦截可能会返回该测试网段中的“假 IP”
_FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)

# 当本地 DNS 解析结果疑似为假 IP 时，尝试使用这些 DoH 服务重新解析
_DOH_SERVERS: tuple[str, ...] = (
    "https://dns.alidns.com/dns-query",
    "https://doh.pub/dns-query",
    "https://doh.360.cn/dns-query",
)


def validate_public_http_url(url: str, *, doh_servers: Sequence[str] = _DOH_SERVERS) -> str:
    """校验 URL 是否可作为外部 HTTP 抓取目标。

    这里只做 URL 安全性校验，不检查页面内容、不识别验证码、不做页面阻断。
    """
    if not url:
        raise UrlSecurityError("URL is empty")

    # URL 前后不能有空白字符，内部也不能包含空白或控制字符
    if url != url.strip() or _CONTROL_OR_SPACE_RE.search(url):
        raise UrlSecurityError("URL contains whitespace or control characters")

    # 禁止反斜杠，避免不同解析器对 URL 的解释不一致
    if "\\" in url:
        raise UrlSecurityError("URL cannot contain backslashes")

    parsed = urlparse(url)

    # 只允许 HTTP 和 HTTPS 协议
    if parsed.scheme not in {"http", "https"}:
        raise UrlSecurityError("URL scheme must be http or https")

    # netloc / hostname 必须存在，例如 https://example.com
    if not parsed.netloc or not parsed.hostname:
        raise UrlSecurityError("URL is missing a hostname")

    # 禁止 URL 中携带用户名或密码，例如 http://user:pass@example.com
    if parsed.username or parsed.password:
        raise UrlSecurityError("URL cannot contain userinfo")

    try:
        port = parsed.port
    except ValueError as exc:
        # parsed.port 在端口非法时会抛出 ValueError
        raise UrlSecurityError("URL port is invalid") from exc

    # 如果显式指定端口，只允许 80 或 443
    if port is not None and port not in _ALLOWED_PORTS:
        raise UrlSecurityError("URL port is not allowed")

    # 解析 hostname，并确保解析结果不落入被阻断的 IP 网段
    _resolve_public_host_ips(parsed.hostname, doh_servers=doh_servers)
    return url


def _resolve_public_host_ips(hostname: str | None, *, doh_servers: Sequence[str]) -> tuple[str, ...]:
    if not hostname:
        raise UrlSecurityError("URL is missing a hostname")

    # 统一 hostname 格式：去除前后空白、尾部点号，并转为小写
    normalized_hostname = hostname.strip().strip(".").lower()
    if not normalized_hostname:
        raise UrlSecurityError("URL is missing a hostname")

    # 显式阻断 localhost 和 .local 域名，避免访问本机或局域网资源
    if normalized_hostname in {"localhost"} or normalized_hostname.endswith(".local"):
        raise UrlSecurityError("Hostname is blocked")

    try:
        # 如果 hostname 本身就是 IP 地址，则直接校验该 IP
        ip = ipaddress.ip_address(normalized_hostname)
    except ValueError:
        ip = None

    if ip is not None:
        _reject_blocked_ip(ip)
        return (str(ip),)

    try:
        # 使用系统 DNS 解析 hostname，限制为 TCP stream 相关地址
        addr_infos = socket.getaddrinfo(normalized_hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlSecurityError(f"Hostname cannot be resolved: {hostname}") from exc

    # 去重并排序，得到该域名解析出的所有 IP
    ips = tuple(sorted({info[4][0] for info in addr_infos}))
    if not ips:
        raise UrlSecurityError(f"Hostname did not resolve to any address: {normalized_hostname}")

    # 如果所有解析结果都是疑似假 IP，则尝试通过 DoH 重新解析
    if _is_all_fake_ips(ips):
        ips = _resolve_with_doh(normalized_hostname, doh_servers=doh_servers)
        if not ips:
            raise UrlSecurityError(
                f"Hostname resolved to fake IP and DoH could not resolve a real address: {normalized_hostname}"
            )

    # 校验每一个解析出的 IP，确保没有落入内网、回环、保留地址等受限网段
    for ip_value in ips:
        _reject_blocked_ip(ipaddress.ip_address(ip_value))

    return tuple(ips)


def _is_all_fake_ips(values: Iterable[str]) -> bool:
    # 判断解析结果是否全部落在 fake IP 网段中
    ips = [ipaddress.ip_address(value) for value in values]
    return bool(ips) and all(
        any(ip in network for network in _FAKE_IP_NETWORKS)
        for ip in ips
    )


def _resolve_with_doh(hostname: str, *, doh_servers: Sequence[str]) -> tuple[str, ...]:
    ips: list[str] = []

    # 依次尝试多个 DoH 服务
    for doh_url in doh_servers:
        # 同时查询 IPv4(A) 和 IPv6(AAAA) 记录
        for record_type in (dns.rdatatype.A, dns.rdatatype.AAAA):
            try:
                query = dns.message.make_query(hostname, record_type)
                response = dns.query.https(query, doh_url, timeout=5.0)
            except Exception:
                # 单个 DoH 服务或单次查询失败时继续尝试下一个
                continue

            # 从 DNS 响应中提取合法 IP 地址
            for rrset in response.answer:
                for item in rrset:
                    value = str(item)
                    try:
                        ipaddress.ip_address(value)
                    except ValueError:
                        # 忽略非 IP 类型的记录
                        continue
                    ips.append(value)

        # 只要当前 DoH 服务解析到了 IP，就直接返回结果
        if ips:
            return tuple(sorted(set(ips)))

    return ()


def _reject_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    # 使用 ipaddress 的内置属性和自定义网段列表进行双重校验
    if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or any(ip in network for network in _BLOCKED_IP_NETWORKS)
    ):
        raise UrlSecurityError(f"Hostname resolves to a blocked IP address: {ip}")
