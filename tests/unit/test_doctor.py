import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from audio_smith import doctor
from audio_smith.cli import app
from audio_smith.config import load_settings


def _check(name: str, ok: bool, required: bool = True) -> doctor.Check:
    def run(_: object) -> doctor.CheckResult:
        return doctor.CheckResult(
            name=name, ok=ok, required=required, detail="d", hint=None if ok else "fix it"
        )

    return doctor.Check(name=name, run=run)


def test_doctor_all_required_pass_exit_0() -> None:
    report = doctor.run_checks(load_settings(), [_check("a", True), _check("b", False, required=False)])
    assert report.ok
    assert len(report.results) == 2


def test_doctor_run_all_fails_when_required_fails() -> None:
    report = doctor.run_checks(load_settings(), [_check("a", False)])
    assert not report.ok
    assert report.results[0].hint == "fix it"


def test_doctor_check_exception_becomes_failure() -> None:
    def boom(_: object) -> doctor.CheckResult:
        raise RuntimeError("kaput")

    report = doctor.run_checks(load_settings(), [doctor.Check(name="x", run=boom)])
    assert not report.ok
    assert "kaput" in report.results[0].detail


def test_doctor_python_version_check_ok() -> None:
    assert doctor.check_python(load_settings()).ok


def test_doctor_ffmpeg_missing_has_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    r = doctor.check_ffmpeg(load_settings())
    assert not r.ok
    assert r.hint


def test_doctor_ffmpeg_older_than_6_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "ffmpeg_version", lambda _: (5, 1))
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    assert not doctor.check_ffmpeg(load_settings()).ok


def test_doctor_ffmpeg_parse_version() -> None:
    assert doctor.parse_ffmpeg_version("ffmpeg version 8.1.1 Copyright") == (8, 1)
    assert doctor.parse_ffmpeg_version("ffmpeg version n6.0-ubuntu") == (6, 0)
    assert doctor.parse_ffmpeg_version("garbage") is None


def test_doctor_cache_dir_writable(tmp_path: Path) -> None:
    assert doctor.check_cache_dir(load_settings()).ok


def test_doctor_disk_space_low_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class U:
        free = 10

    monkeypatch.setattr(doctor.shutil, "disk_usage", lambda _: U())
    assert not doctor.check_disk(load_settings()).ok


def test_doctor_required_failure_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "default_checks", lambda: [_check("a", False)])
    result = CliRunner().invoke(app, ["doctor", "--json"])
    assert result.exit_code == 3
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["results"][0]["hint"] == "fix it"


def test_cli_doctor_table_output_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "default_checks", lambda: [_check("alpha", True)])
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "alpha" in result.output


def test_doctor_json_output_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "default_checks", lambda: [_check("a", True)])
    result = CliRunner().invoke(app, ["doctor", "--json"])
    report = doctor.DoctorReport.model_validate_json(result.output)
    assert report.ok
    assert set(report.results[0].model_dump()) == {"name", "ok", "required", "detail", "hint"}


def test_doctor_disk_space_and_cache_writable_checks() -> None:
    names = {c.name for c in doctor.default_checks()}
    assert {"disk_space", "cache_dir", "python", "ffmpeg"} <= names


def test_doctor_each_failure_has_fix_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class U:
        free = 1

    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("AUDIO_SMITH_CACHE_DIR", str(blocker / "sub"))
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    monkeypatch.setattr(doctor.shutil, "disk_usage", lambda _: U())
    report = doctor.run_checks(load_settings(), doctor.core_checks())
    failures = [r for r in report.results if not r.ok]
    assert {r.name for r in failures} >= {"ffmpeg", "cache_dir", "disk_space"}
    assert all(r.hint for r in failures)
