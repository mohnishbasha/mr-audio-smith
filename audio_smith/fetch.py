"""Safe page fetcher (FR-001): local files and http(s) URLs with an SSRF guard.

Every remote hop is validated and the connection is pinned to the IP that was validated, so a
hostile DNS server cannot answer "public" for the check and "private" for the connect. Redirects
are followed manually so each target passes the same scheme and address checks.
"""

import ipaddress
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

import httpx
from pydantic import BaseModel

from audio_smith import __version__
from audio_smith.config import Settings
from audio_smith.errors import FetchError

MAX_REDIRECTS = 5
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
REMOTE_SCHEMES = frozenset({"http", "https"})
LOCAL_SUFFIXES = {
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}
DEFAULT_ENCODING = "utf-8"
DEFAULT_CONTENT_TYPE = "text/html"
USER_AGENT = f"mr-audio-smith/{__version__} (+https://getaudiosmith.com)"
METADATA_HOSTS = frozenset({"metadata.google.internal"})
METADATA_IPS = frozenset({ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("fd00:ec2::254")})
CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")
SSRF_HINT = "Pass --allow-private only for hosts you trust (for example a local dev server)."
TEXT_TYPES_EXTRA = frozenset({"application/xhtml+xml", "application/markdown"})

Resolver = Callable[[str], list[str]]
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class FetchResult(BaseModel):
    """Decoded page text plus provenance."""

    url: str
    content: str
    content_type: str
    encoding: str
    is_local: bool
    fetched_bytes: int


def default_resolver(host: str) -> list[str]:
    """Resolve a hostname to all of its IP strings via the system resolver."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError(f"Cannot resolve host {host}: {e}", hint="Check the URL and your network.") from e
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def _too_large(limit: int) -> FetchError:
    return FetchError(
        f"Page is too large (limit {limit} bytes)",
        hint="Raise max_fetch_bytes in audio-smith.toml or pick a smaller page.",
    )


def _is_blocked_ip(ip: IPAddress) -> bool:
    """True for any address a public web page should never resolve to."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip in METADATA_IPS:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT_NET:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def _pin_address(host: str, settings: Settings, resolver: Resolver) -> str:
    """Resolve host once, vet every answer, and return the IP to connect to."""
    if host in METADATA_HOSTS and not settings.allow_private:
        raise FetchError(f"Blocked cloud metadata host {host}", hint=SSRF_HINT)
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolver(host)
    if not addresses:
        raise FetchError(f"No addresses found for {host}", hint="Check the URL and your network.")
    for raw in addresses:
        if not settings.allow_private and _is_blocked_ip(ipaddress.ip_address(raw)):
            raise FetchError(
                f"Blocked non-public address {raw} for host {host}",
                hint=SSRF_HINT,
            )
    return addresses[0]


def _read_local(path: Path, settings: Settings, url: str) -> FetchResult:
    content_type = LOCAL_SUFFIXES.get(path.suffix.lower())
    if content_type is None:
        raise FetchError(
            f"Unsupported local file type '{path.suffix}'",
            hint="Use a .html, .htm, .md, or .markdown file.",
        )
    limit = settings.max_fetch_bytes
    try:
        with path.open("rb") as fh:
            raw = fh.read(limit + 1)
    except OSError as e:
        raise FetchError(f"Cannot read {path}: {e.strerror or e}", hint="Check the file path.") from e
    if len(raw) > limit:
        raise _too_large(limit)
    return FetchResult(
        url=url,
        content=raw.decode(DEFAULT_ENCODING, errors="replace"),
        content_type=content_type,
        encoding=DEFAULT_ENCODING,
        is_local=True,
        fetched_bytes=len(raw),
    )


def _parse_content_type(header: str | None) -> tuple[str, str | None]:
    """Split a Content-Type header into (media type, charset or None)."""
    if not header:
        return DEFAULT_CONTENT_TYPE, None
    media, _, params = header.partition(";")
    charset: str | None = None
    for param in params.split(";"):
        key, _, value = param.strip().partition("=")
        if key.lower() == "charset" and value:
            charset = value.strip().strip("\"'").lower()
    return media.strip().lower(), charset


def _decode(raw: bytes, charset: str | None) -> tuple[str, str]:
    """Decode with the declared charset, falling back to UTF-8 with replacement."""
    if charset:
        try:
            return raw.decode(charset, errors="replace"), charset
        except LookupError:
            pass
    return raw.decode(DEFAULT_ENCODING, errors="replace"), DEFAULT_ENCODING


def _check_media_type(media: str) -> None:
    if not (media.startswith("text/") or media in TEXT_TYPES_EXTRA):
        raise FetchError(
            f"Unsupported content type {media}",
            hint="mr-audio-smith reads HTML or Markdown pages only.",
        )


def _read_body(response: httpx.Response, limit: int, deadline: float) -> bytes:
    """Stream the body, aborting as soon as the size or time budget is exceeded."""
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit)
    buf = bytearray()
    for chunk in response.iter_bytes():
        buf.extend(chunk)
        if len(buf) > limit:
            raise _too_large(limit)
        if time.monotonic() > deadline:
            raise FetchError("Fetch exceeded the total time budget", hint="Raise fetch_timeout_s.")
    return bytes(buf)


def _pinned_request(url: str, ip: str) -> tuple[httpx.URL, dict[str, str], dict[str, Any]]:
    """Rewrite the URL to the vetted IP, keeping Host header and TLS SNI on the hostname."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    host_header = host if parts.port is None else f"{host}:{parts.port}"
    if ":" in host:
        host_header = f"[{host}]" if parts.port is None else f"[{host}]:{parts.port}"
    extensions: dict[str, Any] = {"sni_hostname": host} if parts.scheme == "https" else {}
    headers = {"Host": host_header, "User-Agent": USER_AGENT}
    return httpx.URL(url).copy_with(host=ip), headers, extensions


def _hop(
    client: httpx.Client, url: str, settings: Settings, resolver: Resolver, deadline: float
) -> FetchResult | str:
    """Perform one validated request. Returns the page, or the next redirect URL."""
    parts = urlsplit(url)
    if parts.scheme not in REMOTE_SCHEMES or not parts.hostname:
        raise FetchError(
            f"Unsupported or malformed URL '{url}'",
            hint="Use an http, https, or file URL, or a local .html/.md path.",
        )
    ip = _pin_address(parts.hostname, settings, resolver)
    pinned, headers, extensions = _pinned_request(url, ip)
    request = client.build_request(
        "GET", pinned, headers=headers, extensions=extensions, timeout=settings.fetch_timeout_s
    )
    response = client.send(request, stream=True)
    try:
        status = response.status_code
        if status in REDIRECT_STATUSES and response.headers.get("location"):
            return urljoin(url, response.headers["location"])
        if status >= 400:
            raise FetchError(f"HTTP {status} fetching {url}", hint="Check the URL is public and correct.")
        media, charset = _parse_content_type(response.headers.get("content-type"))
        _check_media_type(media)
        raw = _read_body(response, settings.max_fetch_bytes, deadline)
    finally:
        response.close()
    text, encoding = _decode(raw, charset)
    return FetchResult(
        url=url, content=text, content_type=media, encoding=encoding, is_local=False, fetched_bytes=len(raw)
    )


def _fetch_remote(url: str, settings: Settings, client: httpx.Client, resolver: Resolver) -> FetchResult:
    deadline = time.monotonic() + settings.fetch_timeout_s * (MAX_REDIRECTS + 1)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            outcome = _hop(client, current, settings, resolver, deadline)
        except httpx.TimeoutException as e:
            raise FetchError(f"Timed out fetching {current}", hint="Raise fetch_timeout_s or retry.") from e
        except httpx.HTTPError as e:
            raise FetchError(
                f"Network error fetching {current}: {e}", hint="Check the URL and network."
            ) from e
        if isinstance(outcome, FetchResult):
            return outcome
        current = outcome
    raise FetchError(
        f"Too many redirects (more than {MAX_REDIRECTS})",
        hint="The page redirects in a loop; use its final URL.",
    )


def fetch(
    source: str,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
    resolver: Resolver | None = None,
) -> FetchResult:
    """Fetch an http(s) URL or read a local .html/.md file as decoded text.

    Why: a narration tool is handed untrusted URLs, so every hop is scheme-checked, vetted
    against private and metadata ranges, and pinned to the validated IP.

    Args:
        source: http(s) or file URL, or a plain local path.
        settings: Provides max_fetch_bytes, fetch_timeout_s, and allow_private.
        client: Optional httpx client (tests inject a mocked one).
        resolver: Optional hostname to IP-list resolver (tests inject a fake).

    Returns:
        The decoded page and its provenance.

    Raises:
        FetchError: On a blocked scheme or address, HTTP error, timeout, size, or type problem.
    """
    parts = urlsplit(source)
    scheme = parts.scheme.lower()
    if scheme == "file":
        return _read_local(Path(url2pathname(parts.path)), settings, source)
    if scheme in REMOTE_SCHEMES:
        owned = client is None
        http = client or httpx.Client(follow_redirects=False)
        try:
            return _fetch_remote(source, settings, http, resolver or default_resolver)
        finally:
            if owned:
                http.close()
    if (scheme and "://" in source) or scheme in {"javascript", "data", "mailto"}:
        raise FetchError(
            f"Unsupported URL scheme '{scheme}'",
            hint="Use an http, https, or file URL, or a local .html/.md path.",
        )
    return _read_local(Path(source).expanduser(), settings, source)
