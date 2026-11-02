"""The letters-to-a-child example runs end to end with the mock backend and a fake LLM."""

import shutil
from pathlib import Path

import pytest

from audio_smith import api
from audio_smith.config import load_settings
from audio_smith.llm.fake import FakeProvider
from audio_smith.profiles import load_file

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "letters-to-a-child"
VERBATIM = "Be kind, be brave, be curious."
SIGNATURE = "Love you to the moon, Dad"


@pytest.fixture(autouse=True)
def _no_speaker_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from audio_smith import pipeline

    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)


MAIN_CHUNKS = 43
PARENT_CHUNKS = 25


def _main_script() -> str:
    """Long enough to meet the kid-5 length target, so the fake LLM needs no retry."""
    body = "\n\n".join(
        f"## {i:03d}\nA rocket takes a deep breath before it flies. Houston helps Aadi find home."
        for i in range(1, MAIN_CHUNKS + 1)
    )
    return (
        f"{body}\n\n## {MAIN_CHUNKS + 1:03d} {{verbatim}}\n{VERBATIM}"
        f"\n\n## {MAIN_CHUNKS + 2:03d} {{verbatim}}\n{SIGNATURE}"
    )


def _parent_script() -> str:
    return "\n\n".join(
        f"## {i:03d}\nTry one slow breath together before bed. Thank you for helping."
        for i in range(1, PARENT_CHUNKS + 1)
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dest = tmp_path / "site"
    shutil.copytree(EXAMPLE, dest)
    monkeypatch.chdir(dest)
    return dest


def test_examples_letters_to_a_child_profile_override_loads(project: Path) -> None:
    prof = load_file(project / "profiles" / "kid-5.yaml")
    assert prof.id == "kid-5" and prof.version == "1.1.0"
    assert prof.writing.parent_headings == ["A grown-up note"]
    assert prof.lexicon == {"Aadi": "AH-dee", "Houston": "HYOO-stun"}
    settings = load_settings()
    assert settings.default_profile == "kid-5" and settings.default_voice == "dad"
    assert api.resolve_profile(None, settings).version == "1.1.0"


def test_examples_letters_to_a_child_runs_with_mock(project: Path) -> None:
    provider = FakeProvider(responses=[_main_script(), _parent_script()])
    res = api.narrate(
        str(project / "letter-sample.html"),
        llm="fake",
        backend="mock",
        voice="mock-a",
        provider=provider,
    )
    assert res.manifest_path is not None and res.manifest_path.is_file()
    kinds = {t.track.kind for t in res.tracks}
    assert kinds == {"main", "parent"}
    assert (res.out_dir / "letter-sample.mp3").is_file()
    assert res.out_dir == project / "media" / "audio" / "letter-sample"
    assert "Subscribe" not in provider.calls[0][1]
