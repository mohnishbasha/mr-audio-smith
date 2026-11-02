"""Public pipeline API. Every front door (CLI, Studio, server, MCP) calls these functions only.

Stages are functions over typed models and files, so each can be re-run on its own
(Appendix I). I/O boundaries (fetcher, LLM provider, TTS backend) are injectable for tests.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from audio_smith.blocks import BlockDoc, Track, content_hash
from audio_smith.cache import CacheStore
from audio_smith.cache.keys import blocks_key, script_key
from audio_smith.config import Settings, load_settings
from audio_smith.extract import extract as extract_html
from audio_smith.fetch import FetchResult, fetch
from audio_smith.llm import get_provider, provider_label
from audio_smith.llm.base import LLMProvider
from audio_smith.paths import atomic_write, ensure_inside, safe_slug
from audio_smith.profiles import Profile, get_profile
from audio_smith.script.markdown import Script, ScriptMeta, parse_script, serialize
from audio_smith.script.writer import PROMPT_VERSION
from audio_smith.script.writer import write_script as run_writer

Fetcher = Callable[[str, Settings], FetchResult]
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")


class ScriptResult(BaseModel):
    """Outputs of stages 1 and 2."""

    slug: str
    out_dir: Path
    blocks_path: Path
    scripts: dict[str, Path] = Field(default_factory=dict)
    parent_script: Path | None = None
    content_hash: str
    cache_hits: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)


def markdown_to_html(text: str) -> str:
    """Minimal Markdown to HTML so local .md files share the HTML extractor."""
    out: list[str] = ["<article data-narrate>"]
    in_list = False
    for line in text.splitlines():
        heading, item = _MD_HEADING.match(line), _MD_LIST.match(line)
        if in_list and not item:
            out.append("</ul>")
            in_list = False
        if heading:
            level = min(len(heading.group(1)), 4)
            out.append(f"<h{level}>{heading.group(2)}</h{level}>")
        elif item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{item.group(1)}</li>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{line.lstrip('> ')}</blockquote>")
        elif line.strip():
            out.append(f"<p>{line.strip()}</p>")
    out.append("</ul></article>" if in_list else "</article>")
    return "\n".join(out)


def _settings(settings: Settings | None) -> Settings:
    return settings or load_settings()


def extract(
    source: str,
    *,
    settings: Settings | None = None,
    parent_headings: tuple[str, ...] = (),
    force: bool = False,
    fetcher: Fetcher = fetch,
) -> tuple[BlockDoc, bool]:
    """Stage 1: fetch and extract, cached by page bytes. Returns (blocks, cache_hit)."""
    s = _settings(settings)
    page = fetcher(source, s)
    html = markdown_to_html(page.content) if page.url.lower().endswith((".md", ".markdown")) else page.content
    cache = CacheStore(s.cache_dir)
    key = blocks_key(html, parent_headings)
    cached = None if force else cache.get_text("blocks", key, "json")
    if cached is not None:
        return BlockDoc.model_validate_json(cached), True
    doc = extract_html(html, source, parent_headings=parent_headings)
    cache.put_text("blocks", key, "json", doc.to_json())
    return doc, False


def resolve_profile(ref: str | None, settings: Settings) -> Profile:
    return get_profile(ref or settings.default_profile, settings.profiles_dir)


def _script_for_track(
    doc: BlockDoc,
    profile: Profile,
    provider: LLMProvider,
    meta: ScriptMeta,
    track: Track,
    force: bool,
    cache: CacheStore,
) -> tuple[Script, bool, list[str]]:
    key = script_key(meta.content_hash, profile.ref, meta.generated_by, meta.lang, PROMPT_VERSION, track)
    cached = None if force else cache.get_text("scripts", key, "md")
    if cached is not None:
        return parse_script(cached), True, []
    script, warnings = run_writer(doc, profile, provider, meta, track=track)
    cache.put_text("scripts", key, "md", serialize(script))
    return script, False, warnings


def write_script(
    source: str,
    *,
    profile: str | None = None,
    llm: str | None = None,
    backend: str | None = None,
    voice: str | None = None,
    lang: str = "en",
    out: Path | None = None,
    force: bool = False,
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    fetcher: Fetcher = fetch,
) -> ScriptResult:
    """Stages 1 and 2: blocks JSON plus Script Markdown for the main and (if present) parent track."""
    s = _settings(settings)
    prof = resolve_profile(profile, s)
    t0 = time.monotonic()
    doc, blocks_hit = extract(
        source,
        settings=s,
        parent_headings=tuple(prof.writing.parent_headings or ()),
        force=force,
        fetcher=fetcher,
    )
    t1 = time.monotonic()
    llm_spec = llm or s.llm
    llm_provider = provider or get_provider(llm_spec, s)
    chash = content_hash(
        doc,
        profile_id=prof.id,
        profile_version=prof.version,
        backend=backend or s.default_backend,
        voice=voice or s.default_voice or "default",
        lang=lang,
    )
    slug = safe_slug(source)
    out_root = (out or s.out_dir).expanduser()
    out_dir = ensure_inside(out_root, out_root / slug)
    cache = CacheStore(s.cache_dir)
    meta = ScriptMeta(
        source=source, profile=prof.ref, lang=lang, content_hash=chash, generated_by=provider_label(llm_spec)
    )
    script, script_hit, warnings = _script_for_track(doc, prof, llm_provider, meta, "main", force, cache)
    blocks_path = atomic_write(out_dir / f"{slug}.blocks.json", doc.to_json())
    script_path = atomic_write(out_dir / f"{slug}.{lang}.script.md", serialize(script))
    result = ScriptResult(
        slug=slug,
        out_dir=out_dir,
        blocks_path=blocks_path,
        scripts={lang: script_path},
        content_hash=chash,
        cache_hits={"blocks": blocks_hit, "script": script_hit},
        warnings=doc.warnings + warnings,
    )
    if doc.track_blocks("parent") and "parent" in prof.tracks:
        parent_prof = resolve_profile(prof.tracks["parent"], s)
        pmeta = meta.model_copy(update={"profile": parent_prof.ref})
        pscript, _, pwarn = _script_for_track(doc, parent_prof, llm_provider, pmeta, "parent", force, cache)
        result.parent_script = atomic_write(out_dir / f"{slug}.parent.{lang}.script.md", serialize(pscript))
        result.warnings += pwarn
    result.timings = {"extract": round(t1 - t0, 3), "script": round(time.monotonic() - t1, 3)}
    return result
