"""Outbound-request guard for copilot provider URLs typed into the console (decision 0033).

A base URL that a user types is sent from the SERVER, so it must not reach the server's own network
(server-side request forgery). Rules:
* https only (plain http is allowed only for the server's own local Ollama URL, which is not user input);
  no user name or password, query or fragment in the URL.
* The host must resolve, and EVERY address must be public: private, loopback, link-local (incl. cloud metadata
  169.254.169.254), CGNAT, multicast, reserved, unspecified and IPv4-mapped forms of those are blocked.
* The connection is pinned to the checked address (TLS still verifies the host name), so a DNS answer that changes
  between the check and the connection (DNS rebinding) cannot redirect it.
* No redirects are followed; connect timeout 5 s, read timeout 30 s; answers larger than 1 MB are refused.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlsplit

import httpcore
import httpx

MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT = httpx.Timeout(30.0, connect=5.0)
Resolver = Callable[[str, int], list[str]]


class BlockedURL(ValueError):
    """The URL or its address is not allowed. The message is plain language (no key, no internals)."""


def system_resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise BlockedURL(f"the host name {host!r} could not be found (check the base URL)") from None
    return sorted({i[4][0] for i in infos})


def is_blocked_ip(text: str) -> bool:
    ip = ipaddress.ip_address(text.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (not ip.is_global) or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local \
        or ip.is_private or ip.is_unspecified


def check_base_url(url: str) -> tuple[str, int]:
    """Shape checks only (no network). Returns (host, port)."""
    if not url or len(url) > 500:
        raise BlockedURL("the base URL is missing or too long")
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise BlockedURL("the base URL must start with https:// (plain http is allowed only for the local Ollama)")
    if parts.username or parts.password:
        raise BlockedURL("the base URL must not contain a user name or password")
    if parts.query or parts.fragment:
        raise BlockedURL("the base URL must not contain ? or #")
    host = parts.hostname or ""
    if not host:
        raise BlockedURL("the base URL has no host name")
    try:
        port = parts.port or 443
    except ValueError:
        raise BlockedURL("the base URL has an invalid port") from None
    return host, port


def check_public(host: str, port: int, resolve: Resolver | None = None) -> str:
    """Resolve `host` and return the address to connect to; refuse if ANY address is not public."""
    try:
        addrs = [str(ipaddress.ip_address(host))]  # an address typed as the host: no DNS lookup
    except ValueError:
        addrs = (resolve or system_resolve)(host, port)
    if not addrs:
        raise BlockedURL(f"the host name {host!r} could not be found (check the base URL)")
    for a in addrs:
        try:
            blocked = is_blocked_ip(a)
        except ValueError:
            raise BlockedURL(f"the host name {host!r} resolved to an invalid address") from None
        if blocked:
            raise BlockedURL(f"{host} points to a private or internal network address ({a}); only public "
                             "provider addresses are allowed")
    return addrs[0]


class PinnedBackend(httpcore.SyncBackend):
    """Connects only to the pre-checked address for each host; any other host is refused."""

    def __init__(self, pins: dict[str, str]):
        self.pins = pins

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        ip = self.pins.get(host)
        if ip is None:
            raise httpcore.ConnectError(f"connection to {host} was not checked")
        return super().connect_tcp(ip, port, timeout=timeout, local_address=local_address,
                                   socket_options=socket_options)


class PinnedTransport(httpx.HTTPTransport):
    """An httpx transport whose connections go to the pinned address (TLS keeps the real host name for SNI and
    certificate checks)."""

    def __init__(self, pins: dict[str, str]):
        super().__init__(retries=0)
        self._pool = httpcore.ConnectionPool(ssl_context=httpx.create_ssl_context(), max_connections=4,
                                             network_backend=PinnedBackend(pins), retries=0)
