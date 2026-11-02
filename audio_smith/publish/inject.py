"""Marker-based HTML injection (FR-018, Implementation Note 11).

Why string splicing: the user's HTML is never parsed and re-serialized. Offsets
come from the raw text, and only the bytes between the markers (or one new block
after the target element) change, so everything else stays identical.
"""

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from audio_smith.errors import UsageError
from audio_smith.paths import atomic_write

START_MARKER = "<!-- audio-smith:start -->"
END_MARKER = "<!-- audio-smith:end -->"
VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)
RAW_TEXT_TAGS = frozenset({"script", "style", "textarea", "title"})
_TOKEN = re.compile(
    r"<!--.*?-->"
    r"|<(?P<close>/?)(?P<name>[a-zA-Z][^\s/>]*)(?P<attrs>(?:\"[^\"]*\"|'[^']*'|[^'\">])*)>",
    re.DOTALL,
)
_SELECTOR = re.compile(r"^(?P<tag>[a-zA-Z][\w-]*)?(?:#(?P<id>[\w-]+)|\.(?P<cls>[\w-]+))?$")
_ATTR = re.compile(r"""([^\s=/"'>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?""")


@dataclass(frozen=True)
class InjectResult:
    html: str
    changed: bool
    created_markers: bool


def _eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _with_eol(text: str, eol: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", eol)


def _attrs(raw: str) -> dict[str, str]:
    return {m[1].lower(): m[2] or m[3] or m[4] or "" for m in _ATTR.finditer(raw)}


def _matcher(selector: str) -> "re.Match[str]":
    m = _SELECTOR.match(selector.strip())
    if not m or not selector.strip():
        raise UsageError(f"Unsupported selector: {selector!r}", hint="Use a tag, #id, .class, or tag.class.")
    return m


def _matches(sel: "re.Match[str]", name: str, attrs: dict[str, str]) -> bool:
    if sel["tag"] and sel["tag"].lower() != name:
        return False
    if sel["id"] and attrs.get("id") != sel["id"]:
        return False
    return not (sel["cls"] and sel["cls"] not in attrs.get("class", "").split())


def _skip_raw(html: str, name: str, pos: int) -> int:
    """Return the offset of the closing tag of a raw-text element, or end of text."""
    m = re.compile(rf"</{re.escape(name)}\s*>", re.IGNORECASE).search(html, pos)
    return m.start() if m else len(html)


def find_insert_offset(html: str, selector: str) -> int | None:
    """Offset just after the first matching element's closing tag, from raw text."""
    sel = _matcher(selector)
    pos, target, depth = 0, None, 0
    while (m := _TOKEN.search(html, pos)) is not None:
        pos = m.end()
        name = (m["name"] or "").lower()
        if not name:
            continue
        if m["close"]:
            if target and name == target:
                depth -= 1
                if depth == 0:
                    return m.end()
            continue
        if target is None and _matches(sel, name, _attrs(m["attrs"])):
            if name in VOID_TAGS or m["attrs"].rstrip().endswith("/"):
                return m.end()
            target, depth = name, 1
        elif target and name == target:
            depth += 1
        if name in RAW_TEXT_TAGS:
            pos = _skip_raw(html, name, pos)
    return None


def _marker_span(html: str) -> tuple[int, int] | None:
    starts, ends = html.count(START_MARKER), html.count(END_MARKER)
    if starts == 0 and ends == 0:
        return None
    if starts != 1 or ends != 1:
        raise UsageError(
            "Unbalanced or duplicate audio-smith markers.", hint="Keep exactly one start and one end marker."
        )
    s, e = html.index(START_MARKER) + len(START_MARKER), html.index(END_MARKER)
    if e < s:
        raise UsageError("audio-smith end marker comes before the start marker.", hint="Swap or remove them.")
    return s, e


def inject(html: str, snippet: str, *, selector: str = "h1") -> InjectResult:
    """Insert or replace the snippet between markers, touching nothing else."""
    eol = _eol(html)
    body = _with_eol(snippet, eol)
    span = _marker_span(html)
    if span:
        new = html[: span[0]] + eol + body + eol + html[span[1] :]
        return InjectResult(new, new != html, False)
    at = find_insert_offset(html, selector)
    if at is None:
        raise UsageError(
            f"No element matches selector {selector!r}.", hint="Pass --selector with a tag, #id, or .class."
        )
    block = f"{eol}{START_MARKER}{eol}{body}{eol}{END_MARKER}"
    return InjectResult(html[:at] + block + html[at:], True, True)


def unified_diff(old: str, new: str, path: str) -> str:
    """Unified diff of old vs new, labelled with the page path."""
    lines = difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{path}", f"b/{path}"
    )
    return "".join(lines)


def inject_file(path: Path, snippet: str, *, selector: str = "h1", dry_run: bool = False) -> InjectResult:
    """Inject into a file, preserving newline style; dry run writes nothing."""
    old = path.read_bytes().decode("utf-8")
    res = inject(old, snippet, selector=selector)
    if res.changed and not dry_run:
        atomic_write(path, res.html.encode("utf-8"))
    return res
