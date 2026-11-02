from hypothesis import given
from hypothesis import strategies as st

from audio_smith.blocks import Block, BlockDoc, content_hash, hash_text, normalize_text
from audio_smith.extract import extract

BASE = dict(profile_id="kid-5", profile_version="1.0.0", backend="maya2", voice="dad", lang="en")


def _doc(*texts: str) -> BlockDoc:
    return BlockDoc(
        source="x",
        title="T",
        blocks=[Block(id=f"b{i:03d}", type="paragraph", text=t) for i, t in enumerate(texts)],
    )


def test_blocks_hash_whitespace_change_stable() -> None:
    a = extract("<article><h1>T</h1><p>One two three.</p></article>", "x")
    b = extract("<article>\n  <h1> T </h1>\n<p>One   two\n three.</p>\n</article>", "x")
    assert content_hash(a, **BASE) == content_hash(b, **BASE)


def test_blocks_hash_markup_only_change_stable() -> None:
    a = extract("<article><h1>T</h1><p>One <strong>two</strong> three.</p></article>", "x")
    b = extract("<article><div class='wrap'><h1>T</h1><p>One two three.</p></div></article>", "x")
    assert content_hash(a, **BASE) == content_hash(b, **BASE)


def test_blocks_hash_text_change_differs() -> None:
    assert content_hash(_doc("One two."), **BASE) != content_hash(_doc("One three."), **BASE)


def test_blocks_hash_profile_version_change_differs() -> None:
    d = _doc("Hi.")
    assert content_hash(d, **BASE) != content_hash(d, **{**BASE, "profile_version": "1.1.0"})


def test_blocks_hash_backend_voice_language_change_differs() -> None:
    d = _doc("Hi.")
    base = content_hash(d, **BASE)
    for key, value in (("backend", "kokoro"), ("voice", "mom"), ("lang", "hi"), ("profile_id", "kid-8")):
        assert content_hash(d, **{**BASE, key: value}) != base


def test_blocks_normalize_smart_quotes_for_hash_only() -> None:
    assert normalize_text("“Hi”") == "“Hi”"
    assert hash_text("“Hi” it’s") == '"Hi" it\'s'
    assert content_hash(_doc("“Hi”"), **BASE) == content_hash(_doc('"Hi"'), **BASE)


def test_blocks_normalize_strips_emoji_and_space_before_punct() -> None:
    assert normalize_text("Lift off \U0001f680 !  Yay now") == "Lift off! Yay now"


def test_blocks_to_json_uses_schema_alias() -> None:
    assert '"schema": "audio-smith/blocks@1"' in _doc("x").to_json()


@given(
    st.lists(
        st.text(alphabet=st.characters(categories=["L", "N"]), min_size=1, max_size=8), min_size=1, max_size=8
    ),
    st.sampled_from([" ", "  ", "\n", "\t", " \n "]),
)
def test_blocks_hash_whitespace_invariant_property(words: list[str], sep: str) -> None:
    assert content_hash(_doc(" ".join(words)), **BASE) == content_hash(
        _doc(sep + sep.join(words) + sep), **BASE
    )
