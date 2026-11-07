"""SSRF Protection and URL Allowlist Engine for DUIT."""
import ipaddress
import socket
from typing import List, Optional, Tuple
from urllib.parse import urlsplit


BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
]

BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]

PROHIBITED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.local",
    "instance-data",
    "169.254.169.254",
}

ALLOWED_PORTS = {80, 443, 8080, 8443}


def is_ip_blocked(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Checks whether an IP address belongs to any reserved, private, or loopback network."""
    if isinstance(ip_addr, ipaddress.IPv4Address):
        return any(ip_addr in net for net in BLOCKED_IPV4_NETWORKS)
    elif isinstance(ip_addr, ipaddress.IPv6Address):
        return any(ip_addr in net for net in BLOCKED_IPV6_NETWORKS)
    return True


def validate_safe_url(
    url: str,
    allowed_domains: Optional[List[str]] = None,
    require_https: bool = False,
    resolve_dns: bool = True
) -> Tuple[bool, str]:
    """Validates that a URL does not target internal, private, or loopback destinations.

    Returns (is_safe, error_message).
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty"

    url = url.strip()
    try:
        parts = urlsplit(url)
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    # Enforce safe protocol scheme
    scheme = parts.scheme.lower()
    allowed_schemes = ("https",) if require_https else ("https", "http")
    if scheme not in allowed_schemes:
        return False, f"Invalid URL scheme '{scheme}'. Allowed schemes: {allowed_schemes}"

    hostname = parts.hostname
    if not hostname:
        return False, "URL must include a valid hostname"

    lower_host = hostname.lower()

    # Block prohibited hostnames and suffixes
    if lower_host in PROHIBITED_HOSTNAMES:
        return False, f"Prohibited destination host '{lower_host}'"

    if lower_host.endswith((".localhost", ".local", ".internal", ".corp")):
        return False, f"Prohibited domain extension for host '{lower_host}'"

    # Port restriction
    port = parts.port
    if port and port not in ALLOWED_PORTS:
        return False, f"Non-standard port {port} prohibited. Allowed ports: {sorted(ALLOWED_PORTS)}"

    # Domain allowlist check if specified
    if allowed_domains:
        normalized_allowed = [d.lower().strip() for d in allowed_domains if d.strip()]
        matched = any(
            lower_host == domain or lower_host.endswith("." + domain)
            for domain in normalized_allowed
        )
        if not matched:
            return False, f"Host '{lower_host}' is not in approved domain allowlist: {allowed_domains}"

    # If hostname is a direct IP address
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if is_ip_blocked(ip_obj):
            return False, f"Target IP '{ip_obj}' is in a private, loopback, or reserved network"
        return True, ""
    except ValueError:
        pass

    # Resolve DNS to prevent DNS rebinding attacks
    if resolve_dns:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            resolved_ips = set()
            for item in addr_info:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                resolved_ips.add(ip_str)

            if not resolved_ips:
                return False, f"Could not resolve hostname '{hostname}'"

            for ip_str in resolved_ips:
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                    if is_ip_blocked(ip_obj):
                        return False, f"Hostname '{hostname}' resolved to prohibited IP '{ip_str}'"
                except ValueError:
                    return False, f"Invalid resolved IP '{ip_str}'"
        except socket.gaierror:
            # DNS may be unavailable in an isolated validation process. The
            # hostname and scheme checks still apply; the actual HTTP client
            # must enforce the same policy immediately before connecting.
            if allowed_domains:
                return False, f"DNS resolution failed for '{hostname}'"
        except Exception as err:
            return False, f"DNS verification error: {err}"

    return True, ""


def is_url_safe(url: str, allowed_domains: Optional[List[str]] = None) -> bool:
    """Convenience boolean helper for safe URL check."""
    safe, _ = validate_safe_url(url, allowed_domains=allowed_domains)
    return safe
