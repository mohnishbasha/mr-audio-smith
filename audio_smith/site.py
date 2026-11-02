"""Site batch mode (FR-019): narrate every page linked from an index page.

Why a separate module: the CLI, the GitHub Action, and Studio all need the same loop, and the
loop has subtle rules (same-origin only, one shared TTS backend so the model loads once, one bad
page must not sink the batch) that belong in one tested place.
"""

import fnmatch
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

from pydantic import BaseModel
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from audio_smith import api
from audio_smith.config import Settings, load_settings
from audio_smith.errors import UsageError
from audio_smith.fetch import FetchResult, fetch
from audio_smith.paths import ensure_inside
from audio_smith.publish.manifest import Manifest
from audio_smith.tts.registry import get_backend

DEFAULT_MAX_PAGES = 50
DEFAULT_SELECTOR = "h1"
INDEX_FILE = "index.html"
HTTP_SCHEMES = frozenset({"http", "https"})

Status = Literal["cached", "rendered", "failed"]
Fetcher = Callable[[str, Settings], FetchResult]
Narrator = Callable[..., Any]
Injector = Callable[..., Any]
Embedder = Callable[[Manifest], str]


class SiteRow(BaseModel):
    """One line of the batch summary."""

    page: str
    status: Status
    duration_s: float = 0.0
    error: str | None = None
    manifest_path: Path | None = None
    injected: Path | None = None


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.netloc.lower()


def discover_pages(index_html: str, index_url: str, *, match_glob: str, max_pages: int) -> list[str]:
    """Return same-origin page URLs from the index whose file name matches the glob.

    Fragments are dropped and duplicates removed in first-seen order. The cap keeps a
    mistyped glob from queueing a whole site worth of GPU time.
    """
    origin = _origin(index_url)
    seen: dict[str, None] = {}
    for node in HTMLParser(index_html).css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href:
            continue
        url = urldefrag(urljoin(index_url, href))[0]
        parts = urlsplit(url)
        if parts.scheme not in HTTP_SCHEMES or _origin(url) != origin:
            continue
        if fnmatch.fnmatch(Path(unquote(parts.path)).name, match_glob):
            seen.setdefault(url, None)
    return list(seen)[:max_pages]


def local_file_for(inject_root: Path, page_url: str) -> Path:
    """Map a page URL path onto a file under inject_root; refuses paths that escape it."""
    rel = unquote(urlsplit(page_url).path).lstrip("/")
    if not rel or rel.endswith("/"):
        rel += INDEX_FILE
    return ensure_inside(inject_root, inject_root / rel)


def _default_inject(path: Path, snippet: str, *, selector: str, dry_run: bool) -> Any:
    from audio_smith.publish.inject import inject_file  # noqa: PLC0415 - sibling module, loaded on demand

    return inject_file(path, snippet, selector=selector, dry_run=dry_run)


def _default_embed(manifest: Manifest) -> str:
    from audio_smith.publish.embed import EmbedOptions, render_embed  # noqa: PLC0415 - see above

    return render_embed(manifest, EmbedOptions())


def _inject_page(
    page: str,
    manifest: Manifest,
    inject_root: Path,
    selector: str,
    inject: Injector | None,
    embed: Embedder | None,
) -> Path:
    target = local_file_for(inject_root, page)
    if not target.is_file():
        raise UsageError(f"No local file for {page}", hint=f"Expected {target} under --inject-root.")
    snippet = (embed or _default_embed)(manifest)
    (inject or _default_inject)(target, snippet, selector=selector, dry_run=False)
    return target


def _narrate_page(
    page: str,
    narrate: Narrator,
    kwargs: dict[str, Any],
    inject_root: Path | None,
    selector: str,
    inject: Injector | None,
    embed: Embedder | None,
) -> SiteRow:
    start = time.monotonic()
    try:
        res = narrate(page, **kwargs)
        cached = bool(res.tracks) and all(t.cached for t in res.tracks)
        injected = None
        if inject_root is not None and res.manifest is not None:
            injected = _inject_page(page, res.manifest, inject_root, selector, inject, embed)
        return SiteRow(
            page=page,
            status="cached" if cached else "rendered",
            duration_s=round(time.monotonic() - start, 3),
            manifest_path=res.manifest_path,
            injected=injected,
        )
    except Exception as exc:  # one bad page must never abort the batch
        message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
        return SiteRow(
            page=page, status="failed", duration_s=round(time.monotonic() - start, 3), error=message
        )


def narrate_site(
    index_url: str,
    *,
    match_glob: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    inject_root: Path | None = None,
    selector: str = DEFAULT_SELECTOR,
    narrate_kwargs: dict[str, Any],
    fetcher: Fetcher = fetch,
    narrate: Narrator = api.narrate,
    inject: Injector | None = None,
    embed: Embedder | None = None,
) -> list[SiteRow]:
    """Narrate every matching page of a site, sequentially, with one shared TTS backend.

    The index is fetched once. Sequential order is deliberate: a GPU backend cannot overlap
    renders, and a shared backend instance avoids reloading the model for every page.
    """
    settings: Settings = narrate_kwargs.get("settings") or load_settings()
    index = fetcher(index_url, settings)
    pages = discover_pages(index.content, index.url, match_glob=match_glob, max_pages=max_pages)
    kwargs = dict(narrate_kwargs)
    kwargs["settings"] = settings
    if kwargs.get("tts") is None:
        kwargs["tts"] = get_backend(kwargs.get("backend") or settings.default_backend, settings)
    kwargs["fetcher"] = fetcher
    return [_narrate_page(p, narrate, kwargs, inject_root, selector, inject, embed) for p in pages]
