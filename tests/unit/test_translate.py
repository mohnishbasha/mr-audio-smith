from pathlib import Path

import pytest

from audio_smith import api
from audio_smith.errors import PreflightError, ScriptInvalidError
from audio_smith.llm.fake import FakeProvider
from audio_smith.profiles import get_profile
from audio_smith.script.markdown import Chunk, Script, ScriptMeta
from audio_smith.script.translate import alignment_errors, translate_script
from audio_smith.tts.base import Capabilities
from audio_smith.tts.mock import MockBackend

ROOT = Path(__file__).resolve().parents[2]
META = ScriptMeta(source="s", profile="kid-5@1.0.0", lang="en", content_hash="h", generated_by="fake")
SRC = Script(
    meta=META,
    chunks=[
        Chunk(number=1, text="Hello Aadi. [pause 400] Breathe in."),
        Chunk(number=2, text="Your calm spot, Dad", verbatim=True),
    ],
)
HI = "## 001\nनमस्ते आदि। [pause 400] सांस लो।\n\n## 002 {verbatim}\nतुम्हारा शांत कोना, पापा"


@pytest.fixture(autouse=True)
def _no_speaker_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from audio_smith import pipeline

    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)


def test_translate_preserves_chunk_count_and_pauses() -> None:
    out = translate_script(SRC, "hi", get_profile("kid-5"), FakeProvider(responses=[HI]))
    assert out.meta.lang == "hi" and len(out.chunks) == 2
    assert "[pause 400]" in out.chunks[0].text and out.chunks[1].verbatim


def test_translate_misaligned_output_retried_then_fails() -> None:
    bad = "## 001\nनमस्ते आदि। सांस लो।"
    fake = FakeProvider(responses=[bad, bad])
    with pytest.raises(ScriptInvalidError) as e:
        translate_script(SRC, "hi", get_profile("kid-5"), fake)
    assert len(fake.calls) == 2 and "expected 2 chunks" in fake.calls[1][1]
    assert e.value.violations


def test_translate_retry_fixes_dropped_pause() -> None:
    dropped = HI.replace(" [pause 400]", "")
    fake = FakeProvider(responses=[dropped, HI])
    assert translate_script(SRC, "hi", get_profile("kid-5"), fake).chunks[0].text.count("[pause 400]") == 1


def test_translate_alignment_detects_heading_changes() -> None:
    other = SRC.model_copy(update={"chunks": [SRC.chunks[0], Chunk(number=2, text="x")]})
    assert alignment_errors(SRC, other) == ["chunk 002: heading changed"]


def test_translate_backend_lacking_language_fails_preflight(tmp_path: Path) -> None:
    class EnglishOnly(MockBackend):
        def capabilities(self) -> Capabilities:
            return super().capabilities().model_copy(update={"languages": ["en"]})

    page = tmp_path / "letter-calm.html"
    page.write_text(
        (ROOT / "tests/fixtures/pages/letter-calm.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(PreflightError) as e:
        api.narrate(
            str(page),
            llm="fake",
            tts=EnglishOnly(),
            langs=["en", "hi"],
            out=tmp_path / "out",
            provider=FakeProvider(ROOT / "tests/fixtures/llm"),
        )
    assert "hi" in e.value.message


def test_translate_output_named_slug_lang_script_md(tmp_path: Path) -> None:
    page = tmp_path / "letter-calm.html"
    page.write_text(
        (ROOT / "tests/fixtures/pages/letter-calm.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    golden = (ROOT / "tests/fixtures/llm/6252c705b0497217.txt").read_text(encoding="utf-8")
    translated = _hindi_like(golden)
    res = api.narrate(
        str(page),
        llm="fake",
        backend="mock",
        langs=["en", "hi"],
        out=tmp_path / "out",
        provider=FakeProvider(responses=[golden, translated]),
    )
    assert (res.out_dir / "letter-calm.hi.script.md").is_file()
    assert res.manifest is not None


def test_translate_manifest_lists_language_tracks(tmp_path: Path) -> None:
    page = tmp_path / "letter-calm.html"
    page.write_text(
        (ROOT / "tests/fixtures/pages/letter-calm.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    golden = (ROOT / "tests/fixtures/llm/6252c705b0497217.txt").read_text(encoding="utf-8")
    res = api.narrate(
        str(page),
        llm="fake",
        backend="mock",
        langs=["en", "hi"],
        out=tmp_path / "out",
        provider=FakeProvider(responses=[golden, _hindi_like(golden)]),
    )
    assert res.manifest is not None
    assert [(t.lang, t.kind, t.file) for t in res.manifest.tracks] == [
        ("en", "main", "letter-calm.mp3"),
        ("hi", "main", "letter-calm.hi.mp3"),
    ]


def _hindi_like(script_body: str) -> str:
    """A structurally faithful stand-in for a Hindi translation (same chunks, same pause markers)."""
    from audio_smith.script.markdown import parse_chunks
    from audio_smith.script.validate import PAUSE, sanitize_script
    from audio_smith.script.verbatim import enforce_verbatim
    from audio_smith.script.writer import parse_llm_output

    sig = "Your calm spot in every storm, Dad"
    chunks = enforce_verbatim(parse_chunks(parse_llm_output(script_body)), [sig], sig)
    out = []
    for c in sanitize_script(Script(meta=META, chunks=chunks)).chunks:
        pauses = " ".join(f"[pause {ms}]" for ms in PAUSE.findall(c.text))
        out.append(f"## {c.id}{' {verbatim}' if c.verbatim else ''}\nयह एक छोटा वाक्य है। {pauses}".rstrip())
    return "\n\n".join(out)
