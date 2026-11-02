"""Embed snippet generator for `<audio-smith-player>` (FR-017, DESIGN 9).

Why a plain snippet: the output is pasted or injected into someone else's page,
so it must work without JavaScript (native audio plus captions track inside the
component) and must escape every attribute value it emits.
"""

import html
import json
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

from audio_smith import __version__
from audio_smith.master.peaks import peaks_attr
from audio_smith.paths import atomic_write
from audio_smith.publish.manifest import Manifest, Track

PLAYER_FILE = "audio-smith-player.js"
SELF_PATH = "/media/audio/audio-smith-player.js"
JSDELIVR_TEMPLATE = "https://cdn.jsdelivr.net/npm/@mr-audio-smith/player@{version}/dist/" + PLAYER_FILE
PACKAGED_ASSET = ("_assets", "player", PLAYER_FILE)
REPO_DIST = Path(__file__).resolve().parents[2] / "player" / "dist" / PLAYER_FILE
LANG_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
}

Size = Literal["default", "kid"]
Theme = Literal["auto", "light", "dark"]
ScriptMode = Literal["self", "jsdelivr"]


@dataclass(frozen=True)
class EmbedOptions:
    """Knobs for the snippet; `media_base` is prefixed to every media file name."""

    label: str = "Listen"
    size: Size = "default"
    theme: Theme | None = None
    script_mode: ScriptMode = "self"
    self_path: str = SELF_PATH
    media_base: str = ""


def _esc(value: str) -> str:
    """Escape for use inside a quoted HTML attribute."""
    return html.escape(value, quote=True)


def _main_tracks(manifest: Manifest) -> list[Track]:
    """Parent tracks never reach the child player (FR-026)."""
    return [t for t in manifest.tracks if t.kind == "main"]


def _url(opts: EmbedOptions, name: str) -> str:
    return f"{opts.media_base}{name}"


def _tracks_json(tracks: list[Track], opts: EmbedOptions) -> str:
    items = []
    for t in tracks:
        item = {"lang": t.lang, "name": LANG_NAMES.get(t.lang, t.lang.upper()), "src": _url(opts, t.file)}
        if t.captions:
            item["captions"] = _url(opts, t.captions)
        items.append(item)
    return json.dumps(items, separators=(",", ":"), ensure_ascii=False)


def _script_src(opts: EmbedOptions) -> str:
    if opts.script_mode == "jsdelivr":
        return JSDELIVR_TEMPLATE.format(version=__version__)
    return opts.self_path


def _player_attrs(first: Track, tracks: list[Track], opts: EmbedOptions) -> list[str]:
    attrs = [f'src="{_esc(_url(opts, first.file))}"']
    if first.captions:
        attrs.append(f'captions="{_esc(_url(opts, first.captions))}"')
    attrs += [f'label="{_esc(opts.label)}"', f'size="{_esc(opts.size)}"']
    if first.peaks:
        attrs.append(f'peaks="{_esc(peaks_attr(first.peaks))}"')
    if len(tracks) > 1:
        attrs.append(f"tracks='{_esc(_tracks_json(tracks, opts))}'")
    if opts.theme:
        attrs.append(f'theme="{_esc(opts.theme)}"')
    return attrs


def render_embed(manifest: Manifest, opts: EmbedOptions | None = None) -> str:
    """Render the snippet for the first main track, with fallback audio inside.

    Raises:
        ValueError: if the manifest has no main track to embed.
    """
    opts = opts or EmbedOptions()
    tracks = _main_tracks(manifest)
    if not tracks:
        raise ValueError("manifest has no main track to embed")
    first = tracks[0]
    audio = f'<audio controls preload="none" src="{_esc(_url(opts, first.file))}">'
    if first.captions:
        cap = _esc(_url(opts, first.captions))
        audio += (
            f'<track kind="captions" srclang="{_esc(first.lang)}" src="{cap}" '
            f'label="{_esc(LANG_NAMES.get(first.lang, first.lang.upper()))}" default>'
        )
    audio += "</audio>"
    attrs = "\n  ".join(_player_attrs(first, tracks, opts))
    script = f'<script type="module" src="{_esc(_script_src(opts))}"></script>'
    return f"<audio-smith-player\n  {attrs}>\n  {audio}\n</audio-smith-player>\n{script}"


def write_embed(out_dir: Path, slug: str, manifest: Manifest, opts: EmbedOptions | None = None) -> Path:
    """Write `{slug}.embed.html` atomically into out_dir."""
    return atomic_write(out_dir / f"{slug}.embed.html", render_embed(manifest, opts) + "\n")


def _find_player() -> Path | None:
    try:
        packaged = resources.files("audio_smith").joinpath(*PACKAGED_ASSET)
        if packaged.is_file():
            return Path(str(packaged))
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    return REPO_DIST if REPO_DIST.is_file() else None


def copy_player_script(out_dir: Path) -> Path | None:
    """Copy the built player bundle next to the media; None if it is not built yet."""
    src = _find_player()
    if src is None:
        return None
    dest = out_dir / PLAYER_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest
