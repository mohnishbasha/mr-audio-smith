import contextlib
import json
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from audio_smith.blocks import BlockDoc
from audio_smith.errors import ExtractError
from audio_smith.extract import MAX_TOTAL_CHARS, extract

PAGES = Path(__file__).resolve().parents[1] / "fixtures" / "pages"
GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
LETTER_URL = "https://www.aadhish.us/letter-calm-in-the-chaos.html"


def _page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def _texts(doc: BlockDoc) -> list[str]:
    return [b.text for b in doc.blocks]


def test_extract_blocks_data_narrate_present_uses_only_marked_element() -> None:
    doc = extract(_page("data-narrate.html"), "data-narrate.html")
    assert doc.title == "Our Rainy Day"
    assert not any("Decoy" in t for t in _texts(doc))


def test_extract_blocks_article_used_when_no_data_narrate() -> None:
    html = "<html><body><div><p>Outside text here is long enough.</p></div><article><h1>T</h1><p>Inside.</p></article></body></html>"
    assert _texts(extract(html, "x")) == ["T", "Inside."]


def test_extract_blocks_trafilatura_used_when_no_article() -> None:
    para = "This is a long paragraph about the sea and the boats that sail on it every morning. " * 4
    html = f"<html><body><nav>Menu Home About</nav><div class='content'><h2>Sea</h2><p>{para}</p><p>{para}</p></div></body></html>"
    doc = extract(html, "x")
    assert any("boats that sail" in t for t in _texts(doc))
    assert not any("Menu" in t for t in _texts(doc))


def test_extract_blocks_readability_fallback_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    import audio_smith.extract as ex

    monkeypatch.setattr(ex, "_trafilatura_root", lambda _html: None)
    html = "<html><body><div><p>Short.</p></div><section><p>The longest paragraph lives in this section of the page.</p></section></body></html>"
    assert "The longest paragraph lives in this section of the page." in _texts(extract(html, "x"))


def test_extract_no_content_raises_extract_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import audio_smith.extract as ex

    monkeypatch.setattr(ex, "_trafilatura_root", lambda _html: None)
    with pytest.raises(ExtractError):
        extract("<html><body><nav>only nav</nav></body></html>", "x")


def test_extract_empty_article_raises_extract_error() -> None:
    with pytest.raises(ExtractError):
        extract("<html><body><article><script>x</script></article></body></html>", "x")


def test_extract_blocks_nav_header_footer_excluded() -> None:
    html = "<article><nav>Nav</nav><header>Head</header><h1>T</h1><p>Body.</p><footer>Foot</footer><aside>Side</aside></article>"
    assert _texts(extract(html, "x")) == ["T", "Body."]


def test_extract_blocks_scripts_styles_forms_excluded() -> None:
    texts = " ".join(_texts(extract(_page("data-narrate.html"), "x")))
    for bad in ("never read", "color: red", "Search", "Sidebar promo"):
        assert bad not in texts


def test_extract_blocks_emoji_stripped() -> None:
    texts = _texts(extract(_page("letter-calm.html"), LETTER_URL))
    assert all("\U0001f300" not in t and "\U0001f680" not in t and "\U0001f60a" not in t for t in texts)


def test_extract_blocks_regional_indicator_flags_stripped() -> None:
    doc = extract(_page("data-narrate.html"), "x")
    assert "Hello my little explorer, today it rained all day." in _texts(doc)


def test_extract_blocks_skip_attribute_excluded() -> None:
    assert not any("Subscribe" in t for t in _texts(extract(_page("data-narrate.html"), "x")))


def test_extract_blocks_parent_attribute_routed() -> None:
    doc = extract(_page("data-narrate.html"), "x")
    parent = [b.text for b in doc.blocks if b.track == "parent"]
    assert parent == ["A grown-up note", "Wet shoes go by the door, please."]


def test_parent_track_excluded_from_child_blocks() -> None:
    doc = extract(_page("data-narrate.html"), "x")
    assert all("Wet shoes" not in b.text for b in doc.track_blocks("main"))


def test_extract_blocks_types_title_heading_paragraph_list_quote_signature() -> None:
    kinds = [b.type for b in extract(_page("data-narrate.html"), "x").blocks]
    assert kinds[0] == "title"
    for kind in ("heading", "paragraph", "list_item", "quote", "signature"):
        assert kind in kinds


def test_extract_blocks_signature_role_attribute_detected() -> None:
    doc = extract(_page("data-narrate.html"), "x")
    sig = [b for b in doc.blocks if b.type == "signature"]
    assert [s.text for s in sig] == ["Love you to the moon, Mom"]
    assert sig[0].verbatim


def test_extract_blocks_signoff_pattern_detected() -> None:
    doc = extract(_page("letter-calm.html"), LETTER_URL)
    assert doc.blocks[-1].type == "signature"
    assert doc.blocks[-1].text == "Your calm spot in every storm, Dad"
    assert not any("31 October 2026" in t for t in _texts(doc))


def test_extract_blocks_verbatim_attribute_marks_block() -> None:
    doc = extract(_page("data-narrate.html"), "x")
    assert [b.text for b in doc.blocks if b.verbatim and b.type != "signature"] == [
        "Keep this sentence exactly as written."
    ]


def test_extract_blocks_list_items_capture_index_and_nested_heading() -> None:
    items = [b for b in extract(_page("letter-calm.html"), LETTER_URL).blocks if b.type == "list_item"]
    assert [i.index for i in items] == [1, 2, 3, 4, 5, 6]
    assert items[1].heading == "Find the calm eye of the storm"
    assert items[1].text.startswith("A hurricane is wild and windy")


def test_extract_list_item_without_paragraph_strips_number() -> None:
    html = "<article><h1>T</h1><ul><li><h3>Head</h3> 1. Plain item text.</li><li>2) Second.<ul><li>Nested.</li></ul></li></ul></article>"
    items = [b for b in extract(html, "x").blocks if b.type == "list_item"]
    assert items[0].heading == "Head"
    assert items[0].text == "Plain item text."
    assert "Nested." in [i.text for i in items]


def test_extract_list_item_skip_and_parent_attributes() -> None:
    html = "<article><h1>T</h1><ul><li data-narrate='skip'>No.</li><li data-narrate='parent'>Grown-up.</li></ul></article>"
    items = [b for b in extract(html, "x").blocks if b.type == "list_item"]
    assert [(i.text, i.track) for i in items] == [("Grown-up.", "parent")]


def test_extract_blocks_grown_up_note_not_parent_without_attribute() -> None:
    doc = extract(_page("letter-calm.html"), LETTER_URL)
    assert all(b.track == "main" for b in doc.blocks)


def test_extract_blocks_parent_headings_profile_rule_opt_in() -> None:
    doc = extract(_page("letter-calm.html"), LETTER_URL, parent_headings=["A grown-up note"])
    parent = [b.text for b in doc.blocks if b.track == "parent"]
    assert parent[0] == "A grown-up note"
    assert parent[1].startswith("Not every kind of chaos is fun")
    assert len(parent) == 2


def test_extract_parent_headings_routes_heading_tag_sections() -> None:
    html = "<article><h1>T</h1><h2>Kids</h2><p>A.</p><h2>For parents</h2><p>B.</p><h2>More</h2><p>C.</p></article>"
    doc = extract(html, "x", parent_headings=["for parents"])
    assert [(b.text, b.track) for b in doc.blocks if b.track == "parent"] == [
        ("For parents", "parent"),
        ("B.", "parent"),
    ]


def test_extract_letter_calm_matches_golden_blocks() -> None:
    doc = extract(_page("letter-calm.html"), LETTER_URL)
    golden = json.loads((GOLDEN / "letter-calm.blocks.json").read_text(encoding="utf-8"))
    assert json.loads(doc.to_json()) == golden


def test_extract_metadata_title_lang_author_date() -> None:
    doc = extract(_page("letter-calm.html"), LETTER_URL)
    assert (doc.title, doc.lang, doc.date) == ("The Calm Eye of the Storm", "en", "2026-10-31")
    assert doc.image and doc.image.startswith("https://www.aadhish.us/")
    assert extract(_page("data-narrate.html"), "x").author == "Test Parent"


def test_extract_hostile_html_no_crash_within_limits() -> None:
    start = time.monotonic()
    doc = extract(_page("hostile.html"), "hostile.html")
    assert time.monotonic() - start < 20
    assert sum(len(b.text) for b in doc.blocks) <= MAX_TOTAL_CHARS
    assert doc.warnings
    assert not any("alert" in b.text or "base64" in b.text for b in doc.blocks)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.lists(
        st.sampled_from(
            [
                "<p>",
                "</p>",
                "<div>",
                "</div>",
                "<li>",
                "<ol>",
                "<h1>",
                "<h3>",
                "<article>",
                "<script>",
                "<blockquote>",
                "word ",
                "Love, Dad",
                "\U0001f680",
                "<x data-narrate>",
                "&amp;",
                "<",
            ]
        ),
        max_size=40,
    )
)
def test_extract_blocks_fuzz_hypothesis_never_raises(parts: list[str]) -> None:
    with contextlib.suppress(ExtractError):
        extract("".join(parts), "fuzz")


_TAGS = [
    "p",
    "div",
    "section",
    "article",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "blockquote",
    "span",
    "script",
    "style",
    "td",
]
_ATTRS = st.sampled_from(
    ["", ' data-narrate=""', ' class="x"', " hidden", ' aria-hidden="true"', ' onclick="x()"']
)
_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=30)


@st.composite
def _html_tree(draw: st.DrawFn, depth: int = 0) -> str:
    """A syntactically valid but arbitrarily nested and hostile HTML fragment."""
    if depth >= 4 or draw(st.integers(0, 3)) == 0:
        return draw(_TEXT).replace("<", "&lt;")
    tag = draw(st.sampled_from(_TAGS))
    kids = draw(st.lists(_html_tree(depth + 1), max_size=4))
    return f"<{tag}{draw(_ATTRS)}>{''.join(kids)}</{tag}>"


@settings(
    max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
@given(st.lists(_html_tree(), max_size=6), st.booleans())
def test_extract_fuzz_generated_html_trees_never_crash(trees: list[str], wrap_body: bool) -> None:
    html = "".join(trees)
    page = f"<html><body>{html}</body></html>" if wrap_body else html
    with contextlib.suppress(ExtractError):
        doc = extract(page, "fuzz")
        assert sum(len(b.text) for b in doc.blocks) <= MAX_TOTAL_CHARS
        assert not any("<script" in b.text.lower() for b in doc.blocks)
