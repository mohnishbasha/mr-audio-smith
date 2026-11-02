import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from audio_smith import api
from audio_smith.cli import app
from audio_smith.config import load_settings
from audio_smith.errors import ConsentError, UsageError
from audio_smith.tts.base import Capabilities
from audio_smith.tts.mock import MockBackend

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def test_api_render_mock_full_script_masters_track(tmp_path: Path) -> None:
    res = api.render_script(FIX / "scripts" / "valid.script.md", backend="mock", voice="mock-a", out=tmp_path)
    track = res.tracks[0]
    assert track.mp3.is_file() and track.vtt.is_file()
    assert [c.id for c in track.chunks] == ["001", "002", "003", "004"]
    assert abs(track.track.loudness_lufs + 16) <= 1.0


def test_api_render_subset_chunks(tmp_path: Path) -> None:
    res = api.render_script(
        FIX / "scripts" / "valid.script.md", backend="mock", chunks=["2", "4"], out=tmp_path
    )
    assert sorted(res.chunk_files) == ["002", "004"]


def test_api_render_applies_lexicon_at_synthesis_only(tmp_path: Path) -> None:
    seen: list[str] = []

    class Spy(MockBackend):
        def synth(self, text, voice, params):  # type: ignore[no-untyped-def]
            seen.append(text)
            return super().synth(text, voice, params)

    script = FIX / "scripts" / "valid.script.md"
    before = script.read_text(encoding="utf-8")
    api.render_script(script, tts=Spy(), voice="mock-a", out=tmp_path)
    assert seen[0].startswith("My dear AH-dee")
    assert script.read_text(encoding="utf-8") == before


def test_consent_enforced_from_python_api_unregistered_voice(tmp_path: Path) -> None:
    with pytest.raises(ConsentError):
        api.render_script(FIX / "scripts" / "valid.script.md", backend="mock", voice="dad", out=tmp_path)


def test_consent_enforced_from_cli_unregistered_voice_exit_8(tmp_path: Path) -> None:
    import sys

    from audio_smith.cli import main

    argv = [
        "mr-audio-smith",
        "render",
        str(FIX / "scripts" / "valid.script.md"),
        "--backend",
        "mock",
        "--voice",
        "dad",
        "--out",
        str(tmp_path),
    ]
    old = sys.argv
    sys.argv = argv
    try:
        with pytest.raises(SystemExit) as e:
            main()
    finally:
        sys.argv = old
    assert e.value.code == 8


def test_api_render_registered_voice_with_consent_renders(tmp_path: Path) -> None:
    from audio_smith.voices.consent import ConsentRecord
    from audio_smith.voices.registry import add_voice

    settings = load_settings()
    consent = ConsentRecord(
        speaker_name="Fixture Tone",
        relationship="self",
        statement="This is my own voice. I consent to cloning it for narration.",
        date="2026-11-01",
    )
    add_voice(settings.voices_dir, "dad", FIX / "voices" / "clean.wav", consent, display_name="Dad")
    res = api.render_script(FIX / "scripts" / "valid.script.md", backend="mock", voice="dad", out=tmp_path)
    assert res.voice == "dad" and res.tracks[0].mp3.is_file()


def test_api_render_noncommercial_backend_requires_flag(tmp_path: Path) -> None:
    class NC(MockBackend):
        def capabilities(self) -> Capabilities:
            return super().capabilities().model_copy(update={"commercial_ok": False, "license": "CC-BY-NC"})

    with pytest.raises(UsageError):
        api.render_script(FIX / "scripts" / "valid.script.md", tts=NC(), voice="mock-a", out=tmp_path)
    s = load_settings(overrides={"accept_noncommercial": True})
    res = api.render_script(
        FIX / "scripts" / "valid.script.md", tts=NC(), voice="mock-a", out=tmp_path, settings=s
    )
    assert any("non-commercial" in w for w in res.warnings)


def test_api_render_default_voice_is_backend_builtin(tmp_path: Path) -> None:
    res = api.render_script(FIX / "scripts" / "valid.script.md", backend="mock", out=tmp_path)
    assert res.voice == "mock-a"


def test_cli_render_mock_produces_wav_chunks(tmp_path: Path) -> None:
    script = tmp_path / "valid.script.md"
    shutil.copy(FIX / "scripts" / "valid.script.md", script)
    result = CliRunner().invoke(
        app, ["render", str(script), "--backend", "mock", "--out", str(tmp_path / "out"), "--chunks", "1,3"]
    )
    assert result.exit_code == 0, result.output
    assert "chunk 001" in result.output and "chunk 003" in result.output
