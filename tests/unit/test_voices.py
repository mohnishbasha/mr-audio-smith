import os

"""Voice registry, consent, and clip check (TEST_PLAN 5.9)."""

import datetime as dt
import stat
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from audio_smith import doctor
from audio_smith.cli import app
from audio_smith.config import Settings, load_settings
from audio_smith.errors import ConsentError, UsageError
from audio_smith.tts.base import Capabilities, VoiceRef
from audio_smith.voices import registry
from audio_smith.voices.clipcheck import check_clip, normalize_to_24k
from audio_smith.voices.consent import DEFAULT_SELF_STATEMENT, ConsentRecord, require_consent

POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits; Windows is supported via WSL2"
)

VOICES = Path(__file__).parent.parent / "fixtures" / "voices"
REPO = Path(__file__).parent.parent.parent
CLEAN = VOICES / "clean.wav"
runner = CliRunner()


def _consent(**over: object) -> ConsentRecord:
    data: dict[str, object] = {
        "speaker_name": "Fixture Tone",
        "relationship": "self",
        "statement": DEFAULT_SELF_STATEMENT,
        "date": dt.date(2026, 1, 1),
    }
    return ConsentRecord.model_validate({**data, **over})


def _caps(cloning: bool = True) -> Capabilities:
    return Capabilities(
        languages=["en"], cloning=cloning, builtin_voices=["af_heart"], sample_rate=24000,
        max_chars=500, streaming=False, license="mit", commercial_ok=True,
    )  # fmt: skip


def _settings(tmp_path: Path) -> Settings:
    return load_settings()


@pytest.fixture
def vdir(tmp_path: Path) -> Path:
    return tmp_path / "voices"


@pytest.fixture
def added(vdir: Path) -> registry.VoiceRecord:
    return registry.add_voice(vdir, "dad", CLEAN, _consent(), display_name="Dad", reference_text="hello")


def _write_wav(path: Path, data: np.ndarray, rate: int = 24000) -> Path:
    sf.write(path, data, rate, subtype="PCM_16")
    return path


# consent model


def test_consent_registration_requires_all_fields() -> None:
    for missing in ("speaker_name", "relationship", "statement", "date"):
        data = _consent().model_dump()
        del data[missing]
        with pytest.raises(ValidationError):
            ConsentRecord.model_validate(data)
    with pytest.raises(ValidationError):
        _consent(speaker_name="  ")
    with pytest.raises(ValidationError):
        _consent(statement="too short")
    with pytest.raises(ValidationError):
        _consent(date=dt.date.today() + dt.timedelta(days=1))


def test_consent_relationship_only_self_or_written_permission() -> None:
    assert _consent(relationship="written_permission").relationship == "written_permission"
    with pytest.raises(ValidationError):
        _consent(relationship="friend")


def test_consent_clone_unregistered_voice_raises(tmp_path: Path) -> None:
    with pytest.raises(ConsentError) as ei:
        registry.resolve("ghost", load_settings(), _caps())
    assert "voice add" in (ei.value.hint or "")
    with pytest.raises(ConsentError):
        registry.resolve("../etc", load_settings(), _caps())


def test_consent_backend_refuses_clone_without_registry_entry() -> None:
    with pytest.raises(ConsentError):
        require_consent(VoiceRef(id="x", builtin=False, reference_wav=CLEAN))
    require_consent(VoiceRef(id="af_heart", builtin=True))


def test_consent_enforced_from_python_api_and_cli_and_server(vdir: Path, added: registry.VoiceRecord) -> None:
    ref = registry.resolve("dad", load_settings(), _caps())
    assert ref.record_path is not None
    (vdir / "dad" / "voice.yaml").write_text(
        yaml.safe_dump({**added.model_dump(mode="json"), "consent": {"speaker_name": "x"}})
    )
    with pytest.raises(ConsentError) as ei:
        registry.resolve("dad", load_settings(), _caps())
    assert DEFAULT_SELF_STATEMENT not in ei.value.message
    result = runner.invoke(app, ["voice", "check", "dad"])
    assert result.exit_code == 8
    with pytest.raises(ConsentError):
        require_consent(ref)


def test_consent_hash_mismatch_after_tamper_raises(vdir: Path, added: registry.VoiceRecord) -> None:
    ref = registry.resolve("dad", load_settings(), _caps())
    with (vdir / "dad" / "reference.wav").open("ab") as fh:
        fh.write(b"\0")
    with pytest.raises(ConsentError, match="changed"):
        require_consent(ref)
    with pytest.raises(ConsentError):
        require_consent(ref.model_copy(update={"clip_hash": None}))


def test_consent_record_edge_cases(vdir: Path, added: registry.VoiceRecord) -> None:
    ref = registry.resolve("dad", load_settings(), _caps())
    rec = vdir / "dad" / "voice.yaml"
    data = yaml.safe_load(rec.read_text(encoding="utf-8"))
    for patch in ({"reference": "../x.wav"}, {"id": "mom"}, {"reference": "gone.wav"}):
        rec.write_text(yaml.safe_dump({**data, **patch}))
        with pytest.raises(ConsentError):
            require_consent(ref)
    rec.write_text("- just\n- a list\n")
    with pytest.raises(ConsentError):
        require_consent(ref)
    rec.write_text(": : :\n\t-")
    with pytest.raises(ConsentError):
        require_consent(ref)
    rec.unlink()
    with pytest.raises(ConsentError):
        require_consent(ref)


# clip check


def test_clipcheck_clean_fixture_passes() -> None:
    rep = check_clip(CLEAN)
    assert rep.ok and rep.sample_rate == 24000 and rep.snr_db >= 25


def test_clipcheck_too_short_rejected() -> None:
    rep = check_clip(VOICES / "too-short.wav")
    assert not rep.ok and any("too short" in p for p in rep.problems)


def test_clipcheck_too_long_over_30s_rejected(tmp_path: Path) -> None:
    data, _ = sf.read(CLEAN)
    rep = check_clip(_write_wav(tmp_path / "long.wav", np.tile(data, 4)))
    assert any("too long" in p for p in rep.problems)


def test_clipcheck_sample_rate_below_16khz_rejected(tmp_path: Path) -> None:
    data, _ = sf.read(CLEAN)
    rep = check_clip(_write_wav(tmp_path / "lo.wav", data, rate=8000))
    assert any("sample rate" in p for p in rep.problems)


def test_clipcheck_clipping_over_0_1_percent_rejected() -> None:
    rep = check_clip(VOICES / "clipped.wav")
    assert any("clipping" in p for p in rep.problems)


def test_clipcheck_snr_below_25db_rejected() -> None:
    rep = check_clip(VOICES / "noisy.wav")
    assert any("SNR" in p for p in rep.problems)


def test_clipcheck_stereo_downmixed_to_mono(tmp_path: Path) -> None:
    data, _ = sf.read(CLEAN)
    stereo = _write_wav(tmp_path / "st.wav", np.column_stack([data, data]))
    rep = check_clip(stereo)
    assert rep.ok and rep.channels == 2
    out = tmp_path / "out.wav"
    normalize_to_24k(stereo, out)
    assert sf.info(out).channels == 1


def test_clipcheck_edge_cases(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        check_clip(tmp_path / "missing.wav")
    silent = check_clip(_write_wav(tmp_path / "s.wav", np.zeros(24000 * 5)))
    assert any("SNR" in p for p in silent.problems)
    tiny = check_clip(_write_wav(tmp_path / "t.wav", np.zeros(100)))
    assert tiny.snr_db == 0.0
    out = tmp_path / "silent24.wav"
    normalize_to_24k(tmp_path / "s.wav", out)
    assert float(np.max(np.abs(sf.read(out)[0]))) == 0.0


def test_normalize_resamples_and_peaks_at_minus_1_dbfs(tmp_path: Path) -> None:
    t = np.arange(48000 * 4) / 48000
    src = _write_wav(tmp_path / "hi.wav", 0.3 * np.sin(2 * np.pi * 440 * t), rate=48000)
    dst = tmp_path / "n.wav"
    normalize_to_24k(src, dst)
    data, rate = sf.read(dst)
    assert rate == 24000 and abs(len(data) - 24000 * 4) <= 1
    assert abs(20 * np.log10(np.max(np.abs(data))) + 1.0) < 0.05
    low = _write_wav(tmp_path / "lo.wav", 0.3 * np.sin(2 * np.pi * 220 * np.arange(16000 * 4) / 16000), 16000)
    normalize_to_24k(low, dst)
    assert sf.info(dst).samplerate == 24000


# registry


def test_voices_add_stores_24k_mono_reference_copy(vdir: Path, added: registry.VoiceRecord) -> None:
    target = vdir / "dad"
    info = sf.info(target / "reference.24k.wav")
    assert info.samplerate == 24000 and info.channels == 1
    assert len(added.clip_hash) == 64
    assert yaml.safe_load((target / "voice.yaml").read_text(encoding="utf-8"))["clip_hash"] == added.clip_hash
    assert added.clipcheck.sample_rate == 24000


@POSIX_ONLY
def test_voices_permissions_0700_dir_0600_files(vdir: Path, added: registry.VoiceRecord) -> None:
    assert stat.S_IMODE((vdir / "dad").stat().st_mode) == 0o700
    for f in (vdir / "dad").iterdir():
        assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_voices_add_rejects_bad_input(vdir: Path, added: registry.VoiceRecord) -> None:
    with pytest.raises(UsageError, match="already exists"):
        registry.add_voice(vdir, "dad", CLEAN, _consent(), display_name="Dad")
    registry.add_voice(vdir, "dad", CLEAN, _consent(), display_name="Dad 2", replace=True)
    assert registry.get_voice(vdir, "dad").display_name == "Dad 2"
    with pytest.raises(UsageError, match="rejected"):
        registry.add_voice(vdir, "bad", VOICES / "clipped.wav", _consent(), display_name="x")
    assert not (vdir / "bad").exists()
    for bad in ("Bad", "-x", "a/b", "x" * 41, ""):
        with pytest.raises(UsageError):
            registry.add_voice(vdir, bad, CLEAN, _consent(), display_name="x")


def test_voices_list_check_remove_commands(vdir: Path, added: registry.VoiceRecord) -> None:
    assert [v.id for v in registry.list_voices(vdir)] == ["dad"]
    assert registry.list_voices(vdir / "nope") == []
    assert registry.check_voice(vdir, "dad").ok
    registry.remove_voice(vdir, "dad")
    assert registry.list_voices(vdir) == []
    for fn in (registry.remove_voice, registry.get_voice, registry.check_voice):
        with pytest.raises(UsageError):
            fn(vdir, "dad")


@POSIX_ONLY
def test_voices_check_warns_and_fixes_broad_permissions(vdir: Path, added: registry.VoiceRecord) -> None:
    (vdir / "dad").chmod(0o755)
    (vdir / "dad" / "voice.yaml").chmod(0o644)
    res = registry.check_voice(vdir, "dad")
    assert res.ok and len(res.warnings) == 2
    fixed = registry.check_voice(vdir, "dad", fix_permissions=True)
    assert all("fixed" in w for w in fixed.warnings)
    assert registry.check_voice(vdir, "dad").warnings == []


def test_voices_check_reports_clip_and_consent_problems(vdir: Path, added: registry.VoiceRecord) -> None:
    ref = vdir / "dad" / "reference.wav"
    ref.write_bytes(b"not audio")
    res = registry.check_voice(vdir, "dad")
    assert res.consent_error is not None and not res.ok
    (vdir / "dad" / "voice.yaml").unlink()
    assert registry.check_voice(vdir, "dad").consent_error is not None


def test_voices_check_clip_problem_when_clip_degrades(vdir: Path) -> None:
    rec = registry.add_voice(vdir, "dad", CLEAN, _consent(), display_name="Dad")
    noisy = VOICES / "noisy.wav"
    (vdir / "dad" / "reference.wav").write_bytes(noisy.read_bytes())
    data = yaml.safe_load((vdir / "dad" / "voice.yaml").read_text(encoding="utf-8"))
    data["clip_hash"] = registry.file_sha256(noisy)
    (vdir / "dad" / "voice.yaml").write_text(yaml.safe_dump(data))
    res = registry.check_voice(vdir, "dad")
    assert res.consent_error is None and res.clip_problems and rec.id == "dad"


def test_resolve_builtin_vs_cloned(vdir: Path, added: registry.VoiceRecord) -> None:
    s = load_settings()
    b = registry.resolve("af_heart", s, _caps(cloning=False))
    assert b.builtin and b.reference_wav is None
    c = registry.resolve("dad", s, _caps())
    assert not c.builtin and c.reference_text == "hello" and c.clip_hash == added.clip_hash
    assert c.reference_wav == vdir / "dad" / "reference.24k.wav"
    with pytest.raises(UsageError, match="cannot clone") as ei:
        registry.resolve("dad", s, _caps(cloning=False))
    assert "af_heart" in (ei.value.hint or "")


def test_scan_voices_reports_invalid(vdir: Path, added: registry.VoiceRecord) -> None:
    (vdir / "broken").mkdir()
    (vdir / "broken" / "voice.yaml").write_text("id: broken\n")
    (vdir / "stray.txt").write_text("x")
    valid, invalid = registry.scan_voices(vdir)
    assert [v.id for v in valid] == ["dad"] and "broken" in invalid
    (vdir / "broken" / "voice.yaml").write_text(
        yaml.safe_dump({**added.model_dump(mode="json"), "id": "broken", "clipcheck": {}})
    )
    assert "clipcheck" in registry.scan_voices(vdir)[1]["broken"]


def test_voices_gitignore_blocks_reference_wav() -> None:
    def ignored(p: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", p], cwd=REPO, check=False).returncode == 0

    assert ignored("voices/dad/reference.wav")
    assert not ignored("tests/fixtures/voices/clean.wav")


# doctor


def test_doctor_voices_check(vdir: Path) -> None:
    s = load_settings()
    assert doctor.voices_check(s).ok
    registry.add_voice(vdir, "dad", CLEAN, _consent(), display_name="Dad")
    res = doctor.voices_check(s)
    assert res.ok and "dad" in res.detail and not res.required
    (vdir / "dad").chmod(0o755)
    (vdir / "bad").mkdir()
    bad = doctor.voices_check(s)
    assert not bad.ok and "bad" in bad.detail and "dad" in bad.detail and bad.hint
    assert "voices" in [c.name for c in doctor.default_checks()]


# CLI


def test_voices_cli_add_list_check_remove(vdir: Path) -> None:
    add = ["voice", "add", "dad", "--clip", str(CLEAN), "--name", "Fixture Tone", "--relationship", "self"]
    r = runner.invoke(app, [*add, "--yes", "--text", "hello there"])
    assert r.exit_code == 0, r.output
    assert "registered" in r.output
    rec = registry.get_voice(vdir, "dad")
    assert rec.consent.statement == DEFAULT_SELF_STATEMENT and rec.reference_text == "hello there"
    assert "dad" in runner.invoke(app, ["voice", "list"]).output
    (vdir / "bad").mkdir()
    assert "invalid voice bad" in runner.invoke(app, ["voice", "list"]).output
    ok = runner.invoke(app, ["voice", "check", "dad"])
    assert ok.exit_code == 0 and "ok" in ok.output
    (vdir / "dad").chmod(0o755)
    warned = runner.invoke(app, ["voice", "check", "dad", "--fix"])
    assert warned.exit_code == 0 and "fixed" in warned.output
    assert runner.invoke(app, ["voice", "remove", "dad"], input="n\n").exit_code != 0
    assert (vdir / "dad").exists()
    assert runner.invoke(app, ["voice", "remove", "dad", "--yes"]).exit_code == 0
    assert not (vdir / "dad").exists()


def test_cli_voice_add_interactive_consent_prompt(vdir: Path) -> None:
    base = ["voice", "add", "dad", "--clip", str(CLEAN), "--name", "Fixture Tone"]
    r = runner.invoke(app, [*base, "--relationship", "self"], input="\n")
    assert r.exit_code == 0, r.output
    assert registry.get_voice(vdir, "dad").consent.statement == DEFAULT_SELF_STATEMENT
    custom = "I, the speaker, grant written permission for narration use."
    r = runner.invoke(app, [*base, "--relationship", "written_permission", "--replace"], input=custom + "\n")
    assert r.exit_code == 0, r.output
    assert registry.get_voice(vdir, "dad").consent.statement == custom


def test_cli_voice_add_errors(vdir: Path) -> None:
    base = ["voice", "add", "dad", "--clip", str(CLEAN), "--name", "Fixture Tone"]
    r = runner.invoke(app, [*base, "--relationship", "written_permission", "--yes"])
    assert isinstance(r.exception, UsageError)
    r = runner.invoke(app, [*base, "--relationship", "friend", "--yes"])
    assert isinstance(r.exception, UsageError)
    r = runner.invoke(app, [*base, "--relationship", "self", "--yes", "--date", "nope"])
    assert isinstance(r.exception, UsageError)
    r = runner.invoke(app, [*base, "--relationship", "self", "--yes", "--date", "2026-01-02"])
    assert r.exit_code == 0 and registry.get_voice(vdir, "dad").consent.date == dt.date(2026, 1, 2)


def test_cli_voice_check_clip_problems_exit_3(vdir: Path) -> None:
    registry.add_voice(vdir, "dad", CLEAN, _consent(), display_name="Dad")
    noisy = VOICES / "noisy.wav"
    (vdir / "dad" / "reference.wav").write_bytes(noisy.read_bytes())
    data = yaml.safe_load((vdir / "dad" / "voice.yaml").read_text(encoding="utf-8"))
    data["clip_hash"] = registry.file_sha256(noisy)
    (vdir / "dad" / "voice.yaml").write_text(yaml.safe_dump(data))
    r = runner.invoke(app, ["voice", "check", "dad"])
    assert r.exit_code == 3 and "SNR" in r.output


def test_cli_voice_add_explicit_statement_and_unreadable_clip_check(vdir: Path) -> None:
    stmt = "Written permission granted by the speaker for narration."
    base = ["voice", "add", "dad", "--clip", str(CLEAN), "--name", "Fixture Tone"]
    r = runner.invoke(app, [*base, "--relationship", "written_permission", "--statement", stmt])
    assert r.exit_code == 0, r.output
    junk = vdir / "dad" / "reference.wav"
    junk.write_bytes(b"not audio")
    data = yaml.safe_load((vdir / "dad" / "voice.yaml").read_text(encoding="utf-8"))
    data["clip_hash"] = registry.file_sha256(junk)
    (vdir / "dad" / "voice.yaml").write_text(yaml.safe_dump(data))
    res = registry.check_voice(vdir, "dad")
    assert res.consent_error is None and "Cannot read" in res.clip_problems[0]
