from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from audio_smith.errors import ScriptInvalidError
from audio_smith.script.markdown import Chunk, Script, ScriptMeta, parse_script, serialize
from audio_smith.script.validate import plain_text, sanitize, sanitize_script, validate, word_count

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "scripts"
META = ScriptMeta(source="s", profile="kid-5@1.0.0", lang="en", content_hash="h", generated_by="human")


def _script(*texts: str, verbatim: tuple[int, ...] = ()) -> Script:
    return Script(
        meta=META, chunks=[Chunk(number=i, text=t, verbatim=i in verbatim) for i, t in enumerate(texts, 1)]
    )


def test_script_parse_frontmatter_and_numbered_chunks() -> None:
    s = parse_script((FIX / "valid.script.md").read_text())
    assert s.meta.profile == "kid-5@1.0.0"
    assert [c.id for c in s.chunks] == ["001", "002", "003", "004"]
    assert s.chunks[0].text == "My dear Aadi... [pause 600]\nSome days feel like a big, swirly storm!"
    assert s.chunks[3].verbatim
    assert s.chunk("4").text == "Your calm spot in every storm, Dad"


def test_script_parse_valid_fixture_passes() -> None:
    s = parse_script((FIX / "valid.script.md").read_text())
    report = validate(s, max_chunk_chars=360, verbatim_sources=["Your calm spot in every storm, Dad"])
    assert report.ok, report.errors


def test_script_parse_invalid_markers_fixture_rejected() -> None:
    s = parse_script((FIX / "invalid-markers.script.md").read_text())
    report = validate(s, max_chunk_chars=360)
    joined = " ".join(report.errors)
    assert "[laugh]" in joined
    assert "<break" in joined
    assert "5000" in joined


@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter\n## 001\nHi.",
        "---\nschema: audio-smith/script@1\n",
        "---\n- a\n---\n",
        "---\nschema: audio-smith/script@1\nsource: s\nprofile: p@1.0.0\nlang: en\ncontent_hash: h\ngenerated_by: x\nextra: 1\n---\n",
        "---\nschema: audio-smith/script@9\nsource: s\nprofile: p@1.0.0\nlang: en\ncontent_hash: h\ngenerated_by: x\n---\n",
        "---\nschema: audio-smith/script@1\nsource: s\nprofile: p@1.0.0\nlang: en\ncontent_hash: h\ngenerated_by: x\n---\nstray text\n## 001\nHi.",
        "---\nkey: [unclosed\n---\n",
        "---\nsource: s\n---\n",
    ],
)
def test_script_parse_structural_errors_raise(text: str) -> None:
    with pytest.raises(ScriptInvalidError):
        parse_script(text)


@given(
    st.lists(
        st.tuples(
            st.text(alphabet="abc XYZ.,!?", min_size=1, max_size=40).filter(lambda t: t.strip()),
            st.booleans(),
        ),
        min_size=1,
        max_size=6,
    )
)
def test_script_parse_serialize_roundtrip_property(chunks: list[tuple[str, bool]]) -> None:
    s = Script(
        meta=META, chunks=[Chunk(number=i, text=t.strip(), verbatim=v) for i, (t, v) in enumerate(chunks, 1)]
    )
    assert parse_script(serialize(s)) == s
    assert serialize(parse_script(serialize(s))) == serialize(s)


def test_script_validate_unknown_marker_rejected() -> None:
    report = validate(_script("Hello [whisper] there. Fine."), max_chunk_chars=400)
    assert any("[whisper]" in e and "chunk 001" in e for e in report.errors)


def test_script_validate_empty_chunk_rejected() -> None:
    report = validate(_script("Fine. Good.", "[pause 300]"), max_chunk_chars=400)
    assert "chunk 002: empty" in report.errors


def test_script_validate_chunk_over_max_chars_rejected() -> None:
    report = validate(_script("word " * 100), max_chunk_chars=360)
    assert any("exceeds max_chunk_chars 360" in e for e in report.errors)


def test_script_validate_strips_stray_markdown_and_emoji() -> None:
    assert (
        sanitize("# **Big** news \U0001f680 see [here](http://x) and `code`") == "Big news see here and code"
    )
    assert sanitize("- item one\n2. item two\n> quoted") == "item one\nitem two\nquoted"
    assert sanitize("Breathe. *[pause 1000]*") == "Breathe. [pause 1000]"
    s = sanitize_script(_script("**Hi** there \U0001f60a.", "keep **this**", verbatim=(2,)))
    assert s.chunks[0].text == "Hi there."
    assert s.chunks[1].text == "keep **this**"


def test_script_validate_reports_violations_with_chunk_numbers() -> None:
    report = validate(_script("Ok. Ok.", "Bad [x]. Ok.", "", "Ok *two words* here. Ok."), max_chunk_chars=400)
    assert all(e.startswith(("chunk 002", "chunk 003", "chunk 004")) for e in report.errors)
    assert {e[:9] for e in report.errors} == {"chunk 002", "chunk 003", "chunk 004"}


def test_script_validate_verbatim_chunk_changed_rejected() -> None:
    report = validate(
        _script("Hi. Ok.", "Your calm spot, Daddy", verbatim=(2,)),
        max_chunk_chars=400,
        verbatim_sources=["Your calm spot in every storm, Dad"],
    )
    assert any("verbatim chunk differs" in e for e in report.errors)


def test_script_validate_signature_altered_rejected() -> None:
    report = validate(
        _script("Hi. Ok.", "Love you lots, your Dad."),
        max_chunk_chars=400,
        verbatim_sources=["Your calm spot in every storm, Dad"],
    )
    assert any("missing verbatim chunk" in e for e in report.errors)


def test_script_validate_verbatim_ignores_terminal_punct_and_quotes() -> None:
    report = validate(
        _script("Your calm spot in every storm, Dad.", verbatim=(1,)),
        max_chunk_chars=400,
        verbatim_sources=["Your calm spot in every storm, Dad"],
    )
    assert report.ok, report.errors


def test_script_validate_allowed_markers_only_pass() -> None:
    report = validate(_script("Breathe in. [pause 800] And *out*. [pause 100] Done."), max_chunk_chars=400)
    assert report.ok, report.errors


def test_script_validate_numbering_and_no_chunks() -> None:
    s = Script(meta=META, chunks=[Chunk(number=1, text="A. B."), Chunk(number=3, text="C. D.")])
    assert any("expected chunk number 002" in e for e in validate(s, max_chunk_chars=400).errors)
    assert "script has no chunks" in validate(Script(meta=META, chunks=[]), max_chunk_chars=400).errors


def test_script_validate_sentence_count_warning() -> None:
    report = validate(_script("One. Two. Three. Four. Five."), max_chunk_chars=400)
    assert report.ok and report.warnings


def test_script_plain_text_and_word_count() -> None:
    assert plain_text("Hi [pause 300] *there*  friend") == "Hi there friend"
    assert word_count(_script("one two [pause 200] three", "four")) == 4
