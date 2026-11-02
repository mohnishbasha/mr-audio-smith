import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_em_dash", ROOT / "scripts" / "check_em_dash.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_harness_em_dash_hook_fails_on_u2014(tmp_path: Path) -> None:
    f = tmp_path / "bad.md"
    f.write_text(f"calm {chr(0x2014)} storm\n", encoding="utf-8")
    assert mod.main([str(f)]) == 1


def test_scripts_em_dash_clean_file_passes(tmp_path: Path) -> None:
    f = tmp_path / "good.md"
    f.write_text("calm, storm - eye\n", encoding="utf-8")
    assert mod.main([str(f)]) == 0


def test_harness_no_em_dash_in_repo_text_files(monkeypatch: object) -> None:
    import os

    cwd = Path.cwd()
    os.chdir(ROOT)
    try:
        assert mod.find_em_dashes(mod.tracked_files()) == []
    finally:
        os.chdir(cwd)
