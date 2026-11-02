"""Embed snippet and marker injection (TEST_PLAN 5.19, FR-017, FR-018)."""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from selectolax.lexbor import LexborHTMLParser
from typer.testing import CliRunner

from audio_smith import __version__
from audio_smith.cli import app
from audio_smith.errors import UsageError
from audio_smith.publish import embed as embed_mod
from audio_smith.publish.embed import EmbedOptions, copy_player_script, render_embed, write_embed
from audio_smith.publish.inject import END_MARKER, START_MARKER, inject, inject_file, unified_diff
from audio_smith.publish.manifest import Manifest, Track, write_manifest

LETTER = Path(__file__).resolve().parents[1] / "fixtures" / "pages" / "letter-calm.html"
SNIPPET = '<audio-smith-player src="a.mp3"></audio-smith-player>'


def _track(lang: str = "en", kind: str = "main", captions: bool = True) -> Track:
    suffix = "" if lang == "en" else f".{lang}"
    return Track.model_validate(
        {
            "lang": lang,
            "kind": kind,
            "file": f"x{suffix}{'.parent' if kind == 'parent' else ''}.mp3",
            "duration_s": 10.0,
            "loudness_lufs": -16.0,
            "true_peak_dbtp": -1.5,
            "peaks": [0.5] * 28,
            "captions": f"x{suffix}.vtt" if captions else None,
        }
    )


def _manifest(tracks: list[Track]) -> Manifest:
    return Manifest.model_validate(
        {
            "tool_version": "0.1.0",
            "source": "x.html",
            "title": "X",
            "profile": {"id": "p", "version": "1"},
            "backend": {"id": "mock", "model": "m"},
            "llm": "fake",
            "voice_id": "v",
            "content_hash": "h",
            "created_at": "2026-01-01T00:00:00Z",
            "tracks": [t.model_dump() for t in tracks],
            "chunks": [],
        }
    )


def test_embed_snippet_wraps_audio_fallback_inside_component() -> None:
    doc = LexborHTMLParser(render_embed(_manifest([_track()])))
    assert doc.css_first("audio-smith-player > audio[controls]") is not None
    assert doc.css_first("audio[preload=none]") is not None


def test_embed_snippet_includes_captions_track() -> None:
    doc = LexborHTMLParser(render_embed(_manifest([_track()])))
    node = doc.css_first("audio > track[kind=captions]")
    assert node is not None
    assert node.attributes["src"] == "x.vtt"
    assert node.attributes["srclang"] == "en"
    assert "default" in node.attributes


def test_embed_snippet_language_toggle_only_when_multiple_languages() -> None:
    one = render_embed(_manifest([_track()]))
    two = render_embed(_manifest([_track(), _track("hi")]))
    assert "tracks=" not in one
    node = LexborHTMLParser(two).css_first("audio-smith-player")
    assert node is not None
    data = json.loads(node.attributes["tracks"] or "")
    assert [t["lang"] for t in data] == ["en", "hi"]
    assert data[1]["name"] == "Hindi"
    assert data[1]["captions"] == "x.hi.vtt"


def test_embed_excludes_parent_track() -> None:
    out = render_embed(_manifest([_track(), _track("en", "parent")]))
    assert "parent" not in out
    assert "tracks=" not in out


def test_embed_snippet_valid_html() -> None:
    doc = LexborHTMLParser(render_embed(_manifest([_track()]), EmbedOptions(theme="dark", size="kid")))
    player = doc.css_first("audio-smith-player")
    assert player is not None
    attrs = player.attributes
    assert attrs["theme"] == "dark"
    assert attrs["size"] == "kid"
    assert attrs["label"] == "Listen"
    assert len((attrs["peaks"] or "").split(",")) == 28
    assert doc.css_first("script[type=module]") is not None


def test_embed_works_without_js() -> None:
    out = render_embed(_manifest([_track()]))
    assert '<audio controls preload="none" src="x.mp3">' in out
    assert '<track kind="captions"' in out


def test_embed_no_captions_omits_track_and_attr() -> None:
    out = render_embed(_manifest([_track(captions=False)]))
    assert "<track" not in out
    assert "captions=" not in out


def test_embed_no_main_track_raises() -> None:
    with pytest.raises(ValueError, match="no main track"):
        render_embed(_manifest([_track(kind="parent")]))


def test_embed_escapes_hostile_label() -> None:
    hostile = "\"><script>alert(1)</script>'&"
    out = render_embed(_manifest([_track()]), EmbedOptions(label=hostile))
    assert "<script>alert" not in out
    node = LexborHTMLParser(out).css_first("audio-smith-player")
    assert node is not None
    assert node.attributes["label"] == hostile


def test_embed_script_ref_self_hosted_default_path(tmp_path: Path) -> None:
    out = render_embed(_manifest([_track()]))
    assert 'src="/media/audio/audio-smith-player.js"' in out
    fake = tmp_path / "bundle.js"
    fake.write_text("//js", encoding="utf-8")
    dest_dir = tmp_path / "out"
    mp = pytest.MonkeyPatch()
    mp.setattr(embed_mod, "_find_player", lambda: fake)
    try:
        copied = copy_player_script(dest_dir)
    finally:
        mp.undo()
    assert copied == dest_dir / "audio-smith-player.js"
    assert copied.read_text(encoding="utf-8") == "//js"


def test_embed_copy_player_script_none_when_not_built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(embed_mod, "_find_player", lambda: None)
    assert copy_player_script(tmp_path) is None


def test_embed_find_player_returns_path_or_none() -> None:
    found = embed_mod._find_player()
    assert found is None or found.is_file()


def test_embed_script_ref_jsdelivr_pinned_exact_version() -> None:
    out = render_embed(_manifest([_track()]), EmbedOptions(script_mode="jsdelivr"))
    assert (
        f"https://cdn.jsdelivr.net/npm/@mr-audio-smith/player@{__version__}/dist/audio-smith-player.js" in out
    )


def test_embed_media_base_prefix_and_write(tmp_path: Path) -> None:
    path = write_embed(tmp_path, "x", _manifest([_track()]), EmbedOptions(media_base="/media/audio/"))
    assert path.name == "x.embed.html"
    assert 'src="/media/audio/x.mp3"' in path.read_text(encoding="utf-8")


def test_inject_creates_markers_after_selector_when_absent() -> None:
    page = LETTER.read_text(encoding="utf-8")
    res = inject(page, SNIPPET)
    assert res.changed and res.created_markers
    h1_end = page.index("</h1>") + len("</h1>")
    assert res.html[:h1_end] == page[:h1_end]
    assert res.html[h1_end:].startswith(f"\n{START_MARKER}\n{SNIPPET}\n{END_MARKER}")
    assert res.html.endswith(page[h1_end:])


def test_inject_reference_letter_fixture_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "letter.html"
    target.write_bytes(LETTER.read_bytes())
    first = inject_file(target, SNIPPET)
    after_first = target.read_bytes()
    second = inject_file(target, SNIPPET)
    assert first.changed and not second.changed
    assert target.read_bytes() == after_first


def test_inject_idempotent_second_run_no_diff() -> None:
    once = inject("<h1>T</h1><p>x</p>", SNIPPET)
    twice = inject(once.html, SNIPPET)
    assert not twice.changed
    assert twice.html == once.html
    assert not twice.created_markers


def test_inject_replaces_existing_marker_content() -> None:
    page = f"<h1>T</h1>\n{START_MARKER}\nold\n{END_MARKER}<p>x</p>"
    res = inject(page, "new")
    assert res.changed
    assert res.html == f"<h1>T</h1>\n{START_MARKER}\nnew\n{END_MARKER}<p>x</p>"


_SAFE = st.text(alphabet=st.characters(exclude_characters="<>", exclude_categories=["Cs"]), max_size=60)


@settings(max_examples=60, deadline=None)
@given(before=_SAFE, after=_SAFE, old=_SAFE)
def test_inject_outside_markers_untouched(before: str, after: str, old: str) -> None:
    page = f"{before}{START_MARKER}{old}{END_MARKER}{after}"
    res = inject(page, SNIPPET)
    assert res.html.startswith(before + START_MARKER)
    assert res.html.endswith(END_MARKER + after)
    assert inject(res.html, SNIPPET).html == res.html


def test_inject_preserves_original_formatting_no_dom_reserialize() -> None:
    page = "<HTML><BODY   class=a>\n<h1  id='t'>Hi<br>there</h1 >\n<p>unclosed\n<img src=x>\n"
    res = inject(page, SNIPPET)
    marker_block = f"\n{START_MARKER}\n{SNIPPET}\n{END_MARKER}"
    assert res.html == page.replace("</h1 >", "</h1 >" + marker_block)


def test_inject_preserves_crlf() -> None:
    page = "<h1>T</h1>\r\n<p>x</p>\r\n"
    res = inject(page, "a\nb")
    assert "\n" not in res.html.replace("\r\n", "")
    assert inject(res.html, "a\nb").changed is False


def test_inject_file_crlf_bytes_preserved(tmp_path: Path) -> None:
    p = tmp_path / "p.html"
    p.write_bytes(b"<h1>T</h1>\r\n<p>caf\xc3\xa9</p>\r\n")
    inject_file(p, SNIPPET)
    data = p.read_bytes()
    assert data.endswith(b"\r\n<p>caf\xc3\xa9</p>\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"")


@pytest.mark.parametrize(
    ("selector", "page", "after"),
    [
        ("h1", "<h1>a</h1><h1>b</h1>", "<h1>a</h1>"),
        (
            "#hero",
            '<h1>x</h1><div id="hero"><div>in</div></div><p>z</p>',
            '<div id="hero"><div>in</div></div>',
        ),
        (".lead", "<p class='a lead'>x</p><p>y</p>", "<p class='a lead'>x</p>"),
        ("p.lead", '<span class="lead">s</span><p class="lead">x</p>', '<p class="lead">x</p>'),
        (
            "div",
            "<!-- <div>c</div> --><script>var s='<div>'</script><div><div>a</div></div>",
            "<div><div>a</div></div>",
        ),
        ("hr", "<p>a</p><hr><p>b</p>", "<hr>"),
    ],
)
def test_inject_custom_selector_flag(selector: str, page: str, after: str) -> None:
    res = inject(page, SNIPPET, selector=selector)
    expected = page.replace(after, after + f"\n{START_MARKER}\n{SNIPPET}\n{END_MARKER}", 1)
    assert res.html == expected


def test_inject_self_closing_and_unclosed_target() -> None:
    assert inject("<br/><p>", "s", selector="br").html.startswith("<br/>\n<!-- audio-smith:start")
    with pytest.raises(UsageError):
        inject("<h1>never closed", "s")


@pytest.mark.parametrize("selector", ["no-such", "", "a b", "#x"])
def test_inject_selector_not_found_or_bad(selector: str) -> None:
    with pytest.raises(UsageError) as exc:
        inject("<p>x</p>", SNIPPET, selector=selector)
    assert exc.value.hint


@pytest.mark.parametrize(
    "page",
    [
        f"{START_MARKER}a{END_MARKER}{START_MARKER}b{END_MARKER}",
        f"{START_MARKER}only start",
        f"only end{END_MARKER}",
        f"{END_MARKER}x{START_MARKER}",
    ],
)
def test_inject_bad_markers_raise(page: str) -> None:
    with pytest.raises(UsageError):
        inject(page, SNIPPET)


def test_inject_dry_run_prints_unified_diff_writes_nothing(tmp_path: Path) -> None:
    page = tmp_path / "p.html"
    page.write_text("<h1>T</h1>\n", encoding="utf-8")
    manifest = tmp_path / "m.json"
    write_manifest(manifest, _manifest([_track()]))
    result = CliRunner().invoke(app, ["inject", str(page), "--manifest", str(manifest), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "+<!-- audio-smith:start -->" in result.output
    assert page.read_text(encoding="utf-8") == "<h1>T</h1>\n"


def test_inject_cli_writes_then_reports_unchanged(tmp_path: Path) -> None:
    page = tmp_path / "p.html"
    page.write_text("<h1>T</h1>\n", encoding="utf-8")
    manifest = tmp_path / "m.json"
    write_manifest(manifest, _manifest([_track()]))
    args = ["inject", str(page), "--manifest", str(manifest), "--label", "Hear it", "--size", "kid"]
    first = CliRunner().invoke(app, args)
    second = CliRunner().invoke(app, args)
    assert first.exit_code == 0 and 'label="Hear it"' in page.read_text(encoding="utf-8")
    assert "unchanged" in second.output


def test_inject_cli_rejects_bad_size(tmp_path: Path) -> None:
    page = tmp_path / "p.html"
    page.write_text("<h1>T</h1>", encoding="utf-8")
    manifest = tmp_path / "m.json"
    write_manifest(manifest, _manifest([_track()]))
    result = CliRunner().invoke(app, ["inject", str(page), "--manifest", str(manifest), "--size", "huge"])
    assert result.exit_code != 0


def test_unified_diff_labels_path() -> None:
    diff = unified_diff("a\n", "b\n", "p.html")
    assert "--- a/p.html" in diff and "+b" in diff
