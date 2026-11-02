"""Turn an HTML page into an ordered list of typed, narratable blocks (FR-002).

Root selection order: an element marked [data-narrate], then <article>, then trafilatura's
main-content extraction, then a text-density fallback (the "readability" step). HTML is only
parsed, never executed. No magic strings live here: parent routing by heading text happens only
when the caller passes the profile's opt-in `parent_headings`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from audio_smith.blocks import Block, BlockDoc, BlockType, Track, normalize_text
from audio_smith.errors import ExtractError

REMOVE_TAGS = (
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "script",
    "style",
    "noscript",
    "svg",
    "button",
    "iframe",
    "template",
    "object",
    "embed",
    "canvas",
    "select",
    "input",
    "textarea",
    "img",
    "video",
    "audio",
)
HEADING_TAGS = {"h2", "h3", "h4", "h5", "h6"}
BLOCK_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "div",
    "section",
    "article",
    "main",
    "table",
    "figure",
    "pre",
    "dl",
    "details",
}
ROOT_MARKERS = {"", "true", "main", "root"}
MAX_TOTAL_CHARS = 200_000
LABEL_MAX_WORDS = 6
SIGNATURE_MAX_WORDS = 15
SIGNATURE_SEARCH_TAIL = 3
MIN_FALLBACK_CHARS = 40
_TERMINAL = re.compile(r"[.!?\"'”’:;)]$")
_LEADING_NUMBER = re.compile(r"^\d+[.)]?\s+")
_SIGNOFF_START = re.compile(
    r"^(love|with love|all my love|lots of love|yours|your |hugs|xo|forever|always|cheers|best|warmly|"
    r"sincerely|love you|with all|until next time)",
    re.IGNORECASE,
)
_SIGNOFF_END = re.compile(r",\s*(dad|mom|daddy|mommy|papa|mama|grandma|grandpa|me)[.!]?$", re.IGNORECASE)


@dataclass
class _Ctx:
    """Mutable walk state for one extraction."""

    parent_headings: set[str]
    blocks: list[tuple[BlockType, str, Track, int | None, str | None, bool]] = field(default_factory=list)
    title_seen: bool = False
    chars: int = 0
    truncated: bool = False

    def emit(
        self,
        kind: BlockType,
        text: str,
        track: Track,
        *,
        index: int | None = None,
        heading: str | None = None,
        verbatim: bool = False,
    ) -> None:
        clean = normalize_text(text)
        if not clean or self.truncated:
            return
        if self.chars + len(clean) > MAX_TOTAL_CHARS:
            self.truncated = True
            return
        self.chars += len(clean)
        self.blocks.append((kind, clean, track, index, heading and normalize_text(heading), verbatim))


def _attr(node: Node, name: str) -> str | None:
    """Attribute value lowercased; a present but valueless attribute reads as ""."""
    if name not in node.attributes:
        return None
    return (node.attributes.get(name) or "").strip().lower()


def _has_block_child(node: Node) -> bool:
    return any(child.tag in BLOCK_TAGS for child in node.iter())


def _text(node: Node) -> str:
    return node.text(separator=" ", strip=False)


def _is_label(text: str) -> bool:
    words = normalize_text(text).split()
    return 0 < len(words) <= LABEL_MAX_WORDS and not _TERMINAL.search(words[-1])


def _list_item(node: Node, ctx: _Ctx, track: Track, index: int, verbatim: bool) -> None:
    heading_node = next((c for c in node.traverse() if c.tag in HEADING_TAGS), None)
    heading = _text(heading_node) if heading_node is not None else None
    paras = [p for p in node.traverse() if p.tag == "p"]
    if paras:
        body = " ".join(_text(p) for p in paras)
    else:
        body = _text(node)
        if heading:
            body = body.replace(heading, " ", 1)
        body = _LEADING_NUMBER.sub("", normalize_text(body))
    ctx.emit("list_item", body, track, index=index, heading=heading, verbatim=verbatim)
    for nested in node.traverse():
        if nested is not node and nested.tag in ("ul", "ol") and nested.parent is not None:
            _list(nested, ctx, track, verbatim)


def _list(node: Node, ctx: _Ctx, track: Track, verbatim: bool) -> None:
    items = [c for c in node.iter() if c.tag == "li"]
    for i, li in enumerate(items, 1):
        if _attr(li, "data-narrate") == "skip":
            continue
        li_track: Track = "parent" if _attr(li, "data-narrate") == "parent" else track
        _list_item(li, ctx, li_track, i, verbatim or _attr(li, "data-narrate-verbatim") is not None)


def _leaf(node: Node, ctx: _Ctx, track: Track, verbatim: bool) -> None:
    text = _text(node)
    kind: BlockType = "heading" if _is_label(text) else "paragraph"
    ctx.emit(kind, text, track, verbatim=verbatim)


def _container_track(node: Node, ctx: _Ctx, track: Track) -> Track:
    """Opt-in profile rule: a container whose first child is a matching label goes to parent."""
    first = next(iter(node.iter()), None)
    if (
        first is not None
        and ctx.parent_headings
        and not _has_block_child(first)
        and normalize_text(_text(first)).lower() in ctx.parent_headings
    ):
        return "parent"
    return track


def _walk(node: Node, ctx: _Ctx, track: Track = "main", verbatim: bool = False) -> None:
    marker = _attr(node, "data-narrate")
    if marker == "skip":
        return
    if marker == "parent":
        track = "parent"
    verbatim = verbatim or _attr(node, "data-narrate-verbatim") is not None
    tag = node.tag
    if _attr(node, "data-narrate-role") == "signature":
        ctx.emit("signature", _text(node), track, verbatim=True)
    elif tag == "h1":
        ctx.emit("heading" if ctx.title_seen else "title", _text(node), track, verbatim=verbatim)
        ctx.title_seen = True
    elif tag in HEADING_TAGS:
        ctx.emit("heading", _text(node), track, verbatim=verbatim)
    elif tag == "p":
        ctx.emit("paragraph", _text(node), track, verbatim=verbatim)
    elif tag == "blockquote":
        ctx.emit("quote", _text(node), track, verbatim=verbatim)
    elif tag in ("ul", "ol"):
        _list(node, ctx, track, verbatim)
    elif not _has_block_child(node):
        _leaf(node, ctx, track, verbatim)
    else:
        _walk_children(node, ctx, _container_track(node, ctx, track), verbatim)


def _walk_children(node: Node, ctx: _Ctx, track: Track, verbatim: bool) -> None:
    routed: Track | None = None
    for child in node.iter():
        if child.tag in ("h1", *HEADING_TAGS):
            routed = "parent" if normalize_text(_text(child)).lower() in ctx.parent_headings else None
        _walk(child, ctx, routed or track, verbatim)


def _select_root(tree: HTMLParser) -> Node | None:
    for node in tree.css("[data-narrate]"):
        if _attr(node, "data-narrate") in ROOT_MARKERS:
            return node
    return tree.css_first("article")


def _density_root(tree: HTMLParser) -> Node | None:
    """Readability-style fallback: the container with the most direct paragraph text."""
    best: tuple[int, Node | None] = (0, None)
    for node in tree.css("main, section, div, body"):
        score = sum(len(_text(c)) for c in node.iter() if c.tag == "p")
        if score > best[0]:
            best = (score, node)
    return best[1] if best[0] >= MIN_FALLBACK_CHARS else None


def _trafilatura_root(html: str) -> Node | None:
    import trafilatura  # noqa: PLC0415 - heavy import, only on the fallback path

    xml = trafilatura.extract(html, output_format="xml", include_comments=False, include_tables=False)
    if not xml:
        return None
    mapped = re.sub(r"<head\b", "<h2", xml).replace("</head>", "</h2>")
    mapped = re.sub(r"<(/?)list\b", r"<\1ul", mapped)
    mapped = re.sub(r"<(/?)item\b", r"<\1li", mapped)
    mapped = re.sub(r"<(/?)quote\b", r"<\1blockquote", mapped)
    root = HTMLParser(f"<div>{mapped}</div>").css_first("div")
    return root if root is not None and normalize_text(_text(root)) else None


def _is_signoff(text: str) -> bool:
    return len(text.split()) <= SIGNATURE_MAX_WORDS and bool(
        _SIGNOFF_START.search(text) or _SIGNOFF_END.search(text)
    )


def _finalize(raw: list[tuple[BlockType, str, Track, int | None, str | None, bool]]) -> list[Block]:
    """Drop pre-title metadata, detect the sign-off, drop trailing labels after it, assign ids."""
    items = list(raw)
    title_at = next((i for i, b in enumerate(items) if b[0] == "title"), None)
    if title_at:
        items = items[title_at:]
    if not any(b[0] == "signature" for b in items):
        for i in range(len(items) - 1, max(len(items) - 1 - SIGNATURE_SEARCH_TAIL, 0), -1):
            kind, text, track, *_ = items[i]
            if kind in ("paragraph", "heading") and _is_signoff(text):
                items[i] = ("signature", text, track, None, None, True)
                items = items[: i + 1] + [b for b in items[i + 1 :] if b[0] != "heading"]
                break
    return [
        Block(id=f"b{n:03d}", type=k, text=t, track=tr, index=ix, heading=h, verbatim=v or k == "signature")
        for n, (k, t, tr, ix, h, v) in enumerate(items, 1)
    ]


def _meta(tree: HTMLParser, name: str) -> str | None:
    node = tree.css_first(f'meta[name="{name}"], meta[property="{name}"]')
    value = node.attributes.get("content") if node is not None else None
    return value.strip() if value else None


def _doc_meta(tree: HTMLParser) -> dict[str, str | None]:
    html_node = tree.css_first("html")
    lang = (html_node.attributes.get("lang") if html_node is not None else None) or "en"
    time_node = tree.css_first("time[datetime]")
    title_node = tree.css_first("title")
    return {
        "lang": lang.split("-")[0].lower() or "en",
        "author": _meta(tree, "author"),
        "site_name": _meta(tree, "og:site_name"),
        "image": _meta(tree, "og:image"),
        "date": (time_node.attributes.get("datetime") if time_node is not None else None)
        or _meta(tree, "article:published_time"),
        "doc_title": normalize_text(title_node.text()) if title_node is not None else None,
    }


def _strip(root: Node, tags: Iterable[str]) -> None:
    for tag in tags:
        for node in root.css(tag):
            node.decompose()


def extract(html: str, source: str, *, parent_headings: Iterable[str] = ()) -> BlockDoc:
    """Extract narratable blocks from HTML. Raises ExtractError when nothing narratable remains."""
    tree = HTMLParser(html)
    meta = _doc_meta(tree)
    root = _select_root(tree)
    if root is None:
        _strip(tree.root or tree.body or HTMLParser("<div></div>").root, REMOVE_TAGS)  # type: ignore[arg-type]  # root exists for parsed docs
        root = _trafilatura_root(tree.html or "") or _density_root(tree)
    if root is None:
        raise ExtractError(
            f"No narratable content found in {source}", hint="Mark the content with data-narrate."
        )
    _strip(root, REMOVE_TAGS)
    ctx = _Ctx(parent_headings={normalize_text(h).lower() for h in parent_headings})
    _walk_children(root, ctx, "main", _attr(root, "data-narrate-verbatim") is not None)
    blocks = _finalize(ctx.blocks)
    if not blocks:
        raise ExtractError(
            f"No narratable content found in {source}", hint="Mark the content with data-narrate."
        )
    title = next((b.text for b in blocks if b.type == "title"), None) or meta["doc_title"] or source
    warnings = [f"content truncated at {MAX_TOTAL_CHARS} characters"] if ctx.truncated else []
    return BlockDoc(
        source=source,
        title=title,
        lang=meta["lang"] or "en",
        author=meta["author"],
        site_name=meta["site_name"],
        date=meta["date"],
        image=meta["image"],
        blocks=blocks,
        warnings=warnings,
    )
