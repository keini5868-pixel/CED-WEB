"""Descarga HTTP de recursos de usuario — bloquea SSRF (localhost, metadata, LAN)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
}


class UnsafeUrlError(ValueError):
    """URL no permitida para descarga desde el servidor."""


def _hostname(parsed) -> str:
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    return host.strip("[]")


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_private
    )


def assert_public_http_url(url: str) -> str:
    """Valida esquema + host. No sigue redirects. Lanza UnsafeUrlError."""
    raw = (url or "").strip()
    if not raw:
        raise UnsafeUrlError("URL vacía")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Solo se permiten URLs http(s)")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL con credenciales no permitida")
    host = _hostname(parsed)
    if not host:
        raise UnsafeUrlError("Host inválido")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".internal"):
        raise UnsafeUrlError("Host no permitido")
    if host.endswith(".local"):
        raise UnsafeUrlError("Host no permitido")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if not _ip_is_public(ip):
            raise UnsafeUrlError("Dirección no pública")
        return raw
    try:
        infos = socket.getaddrinfo(host, parsed.port or 0, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("No se pudo resolver el host") from exc
    if not infos:
        raise UnsafeUrlError("No se pudo resolver el host")
    for info in infos:
        addr = info[4][0]
        try:
            resolved = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if not _ip_is_public(resolved):
            raise UnsafeUrlError("El host resuelve a una red privada")
    return raw


def fetch_public_http_bytes(
    url: str,
    *,
    timeout: float = 20.0,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> tuple[bytes, str]:
    """GET con validación SSRF en cada hop. Retorna (bytes, content-type)."""
    current = assert_public_http_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            res = client.get(current)
            if res.status_code in {301, 302, 303, 307, 308}:
                location = (res.headers.get("location") or "").strip()
                if not location:
                    raise UnsafeUrlError("Redirect sin Location")
                nxt = urljoin(current, location)
                current = assert_public_http_url(nxt)
                continue
            res.raise_for_status()
            mime = (res.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
            data = res.content
            if len(data) > max_bytes:
                raise UnsafeUrlError("Imagen demasiado grande")
            return data, mime or "application/octet-stream"
    raise UnsafeUrlError("Demasiados redirects")
