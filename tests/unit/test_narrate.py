"""End-to-end pipeline with the fake LLM, mock TTS, and real ffmpeg (no network, no GPU)."""

import json
import time
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from audio_smith import api
from audio_smith.cli import app
from audio_smith.config import load_settings
from audio_smith.errors import ScriptInvalidError
from audio_smith.llm.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "tests" / "fixtures" / "pages"
LLM = ROOT / "tests" / "fixtures" / "llm"
SCHEMA = json.loads((ROOT / "schemas" / "manifest.schema.json").read_text(encoding="utf-8"))
SIG = "Love you to the moon, Mom"


@pytest.fixture(autouse=True)
def _no_speaker_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA has its own tests; loading the embedding model here would only slow the pipeline tests."""
    from audio_smith import pipeline

    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)


def _rainy_main() -> str:
    body = "\n\n".join(
        f"## {i:03d}\nRain is falling on our window today. We can jump in puddles later."
        for i in range(1, 44)
    )
    return (
        body
        + f"\n\n## 044 {{verbatim}}\nKeep this sentence exactly as written.\n\n## 045 {{verbatim}}\n{SIG}"
    )


def _rainy_parent() -> str:
    return "\n\n".join(
        f"## {i:03d}\nWet shoes go by the door, please. Thank you for helping." for i in range(1, 26)
    )


def _letter(tmp_path: Path) -> Path:
    page = tmp_path / "letter-calm.html"
    page.write_text((PAGES / "letter-calm.html").read_text(encoding="utf-8"), encoding="utf-8")
    return page


def test_smoke_run_mock_outputs_exist_and_manifest_validates(tmp_path: Path) -> None:
    res = api.narrate(
        str(_letter(tmp_path)), llm="fake", backend="mock", out=tmp_path / "out", provider=FakeProvider(LLM)
    )
    assert res.manifest_path is not None and res.manifest is not None
    out = res.out_dir
    for name in (
        "letter-calm.mp3",
        "letter-calm.vtt",
        "letter-calm.manifest.json",
        "letter-calm.en.script.md",
    ):
        assert (out / name).is_file(), name
    data = json.loads(res.manifest_path.read_text(encoding="utf-8"))
    jsonschema.validate(data, SCHEMA)
    track = data["tracks"][0]
    assert abs(track["loudness_lufs"] + 16) <= 1 and track["true_peak_dbtp"] <= -1.5
    assert len(track["peaks"]) == 28 and track["captions"] == "letter-calm.vtt"
    assert data["voice_id"] == "mock-a" and data["profile"] == {"id": "kid-5", "version": "1.0.0"}


def test_cache_unchanged_rerun_under_2s(tmp_path: Path) -> None:
    page = _letter(tmp_path)
    kwargs = dict(llm="fake", backend="mock", out=tmp_path / "out", provider=FakeProvider(LLM))
    api.narrate(str(page), **kwargs)
    start = time.monotonic()
    again = api.narrate(str(page), **kwargs)
    assert time.monotonic() - start < 2.0
    assert all(t.cached for t in again.tracks)


def test_narrate_dry_run_plans_without_audio(tmp_path: Path) -> None:
    res = api.narrate(
        str(_letter(tmp_path)),
        llm="fake",
        backend="mock",
        out=tmp_path / "out",
        dry_run=True,
        provider=FakeProvider(LLM),
    )
    assert res.manifest_path is None and res.plan
    assert not (res.out_dir / "letter-calm.mp3").exists()


def test_narrate_approve_uses_edited_script(tmp_path: Path) -> None:
    def editor(path: Path) -> None:
        text = path.read_text(encoding="utf-8").replace("## 001\n", "## 001\nHello from the editor. ", 1)
        path.write_text(text, encoding="utf-8")

    res = api.narrate(
        str(_letter(tmp_path)),
        llm="fake",
        backend="mock",
        out=tmp_path / "out",
        approve=True,
        editor=editor,
        provider=FakeProvider(LLM),
    )
    assert res.manifest is not None and res.manifest.approved
    assert "Hello from the editor." in (res.out_dir / "letter-calm.vtt").read_text(encoding="utf-8")


def test_narrate_approve_invalid_edit_rejected(tmp_path: Path) -> None:
    def editor(path: Path) -> None:
        path.write_text(path.read_text(encoding="utf-8") + "\n## 099\n[laugh] nope.\n", encoding="utf-8")

    with pytest.raises(ScriptInvalidError):
        api.narrate(
            str(_letter(tmp_path)),
            llm="fake",
            backend="mock",
            out=tmp_path / "out",
            approve=True,
            editor=editor,
            provider=FakeProvider(LLM),
        )


def test_parent_track_rendered_separately_never_in_child_track(tmp_path: Path) -> None:
    page = tmp_path / "rainy-day.html"
    page.write_text((PAGES / "data-narrate.html").read_text(encoding="utf-8"), encoding="utf-8")
    provider = FakeProvider(responses=[_rainy_main(), _rainy_parent()])
    res = api.narrate(str(page), llm="fake", backend="mock", out=tmp_path / "out", provider=provider)
    kinds = {t.track.kind: t for t in res.tracks}
    assert set(kinds) == {"main", "parent"}
    assert kinds["parent"].mp3.name == "rainy-day.parent.mp3"
    assert "Wet shoes" not in kinds["main"].vtt.read_text(encoding="utf-8")
    assert "Wet shoes" in kinds["parent"].vtt.read_text(encoding="utf-8")


def test_python_api_package_level_narrate_exposed() -> None:
    import audio_smith

    assert audio_smith.narrate is api.narrate


def test_cli_run_mock_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import audio_smith.api as api_mod

    monkeypatch.setattr(api_mod, "get_provider", lambda spec, s: FakeProvider(LLM))
    result = CliRunner().invoke(
        app,
        ["run", str(_letter(tmp_path)), "--llm", "fake", "--backend", "mock", "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 0, result.output
    assert "manifest:" in result.output and "LUFS" in result.output
    dry = CliRunner().invoke(
        app,
        [
            "run",
            str(_letter(tmp_path)),
            "--llm",
            "fake",
            "--backend",
            "mock",
            "--out",
            str(tmp_path / "out"),
            "--dry-run",
        ],
    )
    assert dry.exit_code == 0 and "script en" in dry.output


def test_api_render_settings_default_backend_mock(tmp_path: Path) -> None:
    s = load_settings(overrides={"default_backend": "mock"})
    res = api.render_script(
        ROOT / "tests" / "fixtures" / "scripts" / "valid.script.md", out=tmp_path, settings=s
    )
    assert res.backend == "mock" and res.tracks


def test_narrate_embed_options_from_settings(tmp_path: Path) -> None:
    s = load_settings(
        overrides={"embed_label": "Listen to Dad", "embed_size": "kid", "embed_media_base": "/m/"}
    )
    res = api.narrate(
        str(_letter(tmp_path)),
        llm="fake",
        backend="mock",
        out=tmp_path / "out",
        settings=s,
        provider=FakeProvider(LLM),
    )
    assert res.embed_path is not None
    html = res.embed_path.read_text(encoding="utf-8")
    assert 'label="Listen to Dad"' in html and 'size="kid"' in html and 'src="/m/letter-calm.mp3"' in html


def test_narrate_inject_writes_markers_once(tmp_path: Path) -> None:
    page = _letter(tmp_path)
    kwargs = dict(llm="fake", backend="mock", out=tmp_path / "out", provider=FakeProvider(LLM), inject=page)
    first = api.narrate(str(page), **kwargs)
    second = api.narrate(str(page), **kwargs)
    text = page.read_text(encoding="utf-8")
    assert first.inject_changed and not second.inject_changed
    assert text.count("<!-- audio-smith:start -->") == 1
