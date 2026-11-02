# mypy: disable-error-code="no-untyped-call"
"""ID3 tags and cover art for mastered MP3s (FR-014)."""

import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, ID3NoHeaderError

from audio_smith.config import Settings
from audio_smith.errors import AudioSmithError, FetchError
from audio_smith.fetch import (
    MAX_REDIRECTS,
    REDIRECT_STATUSES,
    REMOTE_SCHEMES,
    Resolver,
    _pin_address,
    _pinned_request,
    _read_body,
    default_resolver,
)

DEFAULT_MAX_COVER_BYTES = 1_048_576
ID3_ENCODING_UTF8 = 3
APIC_FRONT_COVER = 3
ID3_VERSION = 3
DEFAULT_PORTS = {"http": 80, "https": 443}
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

ByteFetcher = Callable[[str], bytes]


def detect_image_mime(data: bytes) -> str | None:
    """Mime type from magic bytes (never trust the URL or header); jpeg and png only."""
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    return None


def write_tags(mp3: Path, *, title: str, artist: str, album: str, date: str, cover: bytes | None) -> None:
    """Write TIT2, TPE1, TALB, TDRC and an optional front cover, replacing existing tags."""
    try:
        tags = ID3(mp3)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("APIC")
    tags.add(TIT2(encoding=ID3_ENCODING_UTF8, text=title))
    tags.add(TPE1(encoding=ID3_ENCODING_UTF8, text=artist))
    tags.add(TALB(encoding=ID3_ENCODING_UTF8, text=album))
    tags.add(TDRC(encoding=ID3_ENCODING_UTF8, text=date))
    mime = detect_image_mime(cover) if cover else None
    if cover and mime:
        tags.add(APIC(encoding=ID3_ENCODING_UTF8, mime=mime, type=APIC_FRONT_COVER, desc="Cover", data=cover))
    tags.save(mp3, v2_version=ID3_VERSION)


def _origin(url: str) -> tuple[str, str, int] | None:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS or not parts.hostname:
        return None
    try:
        port = parts.port or DEFAULT_PORTS[scheme]
    except ValueError:
        return None
    return scheme, parts.hostname.lower(), port


def fetch_cover(
    image_url: str, page_url: str, fetcher: ByteFetcher, max_bytes: int = DEFAULT_MAX_COVER_BYTES
) -> bytes | None:
    """Return cover bytes only for a same-origin jpeg or png no larger than max_bytes.

    Why: an og:image on another host would make the tool request an attacker-chosen URL and
    embed unvetted content, so cross-origin art is skipped. Failures never abort the render.
    """
    page_origin = _origin(page_url)
    absolute = urljoin(page_url, image_url)
    if page_origin is None or _origin(absolute) != page_origin:
        return None
    try:
        data = fetcher(absolute)
    except (AudioSmithError, httpx.HTTPError, OSError, ValueError):
        return None
    if len(data) > max_bytes or detect_image_mime(data) is None:
        return None
    return data


def http_get_bytes(
    url: str,
    settings: Settings,
    *,
    max_bytes: int = DEFAULT_MAX_COVER_BYTES,
    client: httpx.Client | None = None,
    resolver: Resolver | None = None,
) -> bytes:
    """GET raw bytes with the same SSRF guard (vetted, pinned IP, manual redirects) as fetch()."""
    owned = client is None
    http = client or httpx.Client(follow_redirects=False)
    resolve = resolver or default_resolver
    deadline = time.monotonic() + settings.fetch_timeout_s * (MAX_REDIRECTS + 1)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(current)
            if parts.scheme not in REMOTE_SCHEMES or not parts.hostname:
                raise FetchError(
                    f"Unsupported or malformed URL '{current}'", hint="Use an http or https URL."
                )
            ip = _pin_address(parts.hostname, settings, resolve)
            pinned, headers, extensions = _pinned_request(current, ip)
            request = http.build_request(
                "GET", pinned, headers=headers, extensions=extensions, timeout=settings.fetch_timeout_s
            )
            response = http.send(request, stream=True)
            try:
                if response.status_code in REDIRECT_STATUSES and response.headers.get("location"):
                    current = urljoin(current, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise FetchError(
                        f"HTTP {response.status_code} fetching {current}", hint="Check the image URL."
                    )
                return _read_body(response, max_bytes, deadline)
            finally:
                response.close()
        raise FetchError("Too many redirects", hint="Use the image's final URL.")
    except httpx.HTTPError as e:
        raise FetchError(f"Network error fetching {url}: {e}", hint="Check the URL and network.") from e
    finally:
        if owned:
            http.close()
