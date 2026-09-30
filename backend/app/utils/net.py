"""Network helpers shared by outbound-request code (SSRF protection)."""

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})


def _resolve(hostname: str, port: int | None) -> list[str]:
    """Resolve *hostname* to a list of IP address strings (patched in tests)."""
    return [info[4][0] for info in socket.getaddrinfo(hostname, port)]


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only for globally routable unicast addresses."""
    # Unwrap IPv4-mapped IPv6 (::ffff:10.0.0.1) so it cannot bypass the checks.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False
    # Catches remaining non-global ranges such as CGNAT (100.64.0.0/10).
    return ip.is_global


def is_safe_url(url: str, *, allow_private: bool = False) -> bool:
    """Return True if *url* is http(s) and every address it resolves to is public.

    Hostnames that fail to resolve are rejected. With ``allow_private=True``
    only the scheme/hostname checks are applied (for self-hosters targeting
    LAN services).
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        port = parsed.port  # raises ValueError on a malformed port
        addresses = _resolve(hostname, port)
        if not addresses:
            return False
        if allow_private:
            return True
        return all(is_public_ip(ipaddress.ip_address(a.split("%")[0])) for a in addresses)
    except Exception:
        return False
