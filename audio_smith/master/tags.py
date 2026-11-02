"""ID3 tags and cover art for mastered MP3s (FR-014).

Tags are written by ffmpeg in a separate process (stream copy, no re-encode) rather than by a
GPL-licensed tagging library, so the MIT core links no copyleft code.
"""

import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from audio_smith import proc
from audio_smith.config import Settings
from audio_smith.errors import AudioSmithError, FetchError, MasteringError
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
ID3_VERSION = 3
TAG_TIMEOUT_S = 60
MIME_EXT = {"image/jpeg": "jpg", "image/png": "png"}
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


def _tag_args(src: Path, dst: Path, meta: dict[str, str], cover: Path | None) -> list[str]:
    args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src)]
    if cover is not None:
        args += [
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c:v",
            "copy",
            "-disposition:v",
            "attached_pic",
            "-metadata:s:v",
            "title=Cover",
            "-metadata:s:v",
            "comment=Cover (front)",
        ]
    else:
        args += ["-map", "0:a"]
    args += ["-c:a", "copy", "-map_metadata", "-1", "-id3v2_version", str(ID3_VERSION)]
    for key, value in meta.items():
        args += ["-metadata", f"{key}={value}"]
    return [*args, str(dst)]


def write_tags(mp3: Path, *, title: str, artist: str, album: str, date: str, cover: bytes | None) -> None:
    """Replace title, artist, album, date, and the optional front cover (jpeg or png only)."""
    mime = detect_image_mime(cover) if cover else None
    meta = {"title": title, "artist": artist, "album": album, "date": date}
    with tempfile.TemporaryDirectory(dir=mp3.parent) as tmp:
        cover_path = None
        if cover is not None and mime is not None:
            cover_path = Path(tmp) / f"cover.{MIME_EXT[mime]}"
            cover_path.write_bytes(cover)
        out = Path(tmp) / mp3.name
        try:
            proc.run(_tag_args(mp3, out, meta, cover_path), timeout=TAG_TIMEOUT_S)
        except Exception as e:
            raise MasteringError(
                f"Could not write tags to {mp3.name}: {e}", hint="Check that ffmpeg works."
            ) from e
        out.replace(mp3)


def read_tags(mp3: Path) -> dict[str, str]:
    """Tags as ffprobe reports them, plus `cover` = codec of an attached picture (tests and Studio)."""
    raw = proc.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format_tags:stream=codec_name,codec_type",
            "-of",
            "json",
            str(mp3),
        ],
        timeout=TAG_TIMEOUT_S,
    )
    data = json.loads(raw)
    tags = {k.lower(): str(v) for k, v in data.get("format", {}).get("tags", {}).items()}
    pics = [s["codec_name"] for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if pics:
        tags["cover"] = pics[0]
    return tags


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
