import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_coverage", ROOT / "scripts" / "check-coverage.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _cov(pct_by_file: dict[str, tuple[int, int]], overall: float) -> dict[str, object]:
    files = {f: {"summary": {"covered_lines": c, "num_statements": t}} for f, (c, t) in pct_by_file.items()}
    return {"files": files, "totals": {"percent_covered": overall}}


def test_scripts_check_coverage_module_under_target_fails(tmp_path: Path) -> None:
    cov = tmp_path / "c.json"
    cov.write_text(json.dumps(_cov({"audio_smith/blocks.py": (50, 100)}, 90.0)))
    thr = tmp_path / "t.toml"
    thr.write_text('[python]\n"audio_smith/blocks.py" = 95\noverall = 85\n', encoding="utf-8")
    assert mod.main([str(cov), str(thr)]) == 1


def test_scripts_check_coverage_directory_prefix_aggregates(tmp_path: Path) -> None:
    cov = tmp_path / "c.json"
    files = {
        "audio_smith/tts/a.py": (90, 100),
        "audio_smith/tts/b.py": (100, 100),
        "audio_smith/x.py": (0, 50),
    }
    cov.write_text(json.dumps(_cov(files, 90.0)))
    thr = tmp_path / "t.toml"
    thr.write_text(
        '[python]\n"audio_smith/tts" = 85\n"audio_smith/qa" = 80\noverall = 85\n', encoding="utf-8"
    )
    assert mod.main([str(cov), str(thr)]) == 0


def test_scripts_check_coverage_overall_under_target_fails(tmp_path: Path) -> None:
    cov = tmp_path / "c.json"
    cov.write_text(json.dumps(_cov({}, 70.0)))
    thr = tmp_path / "t.toml"
    thr.write_text("[python]\noverall = 85\n", encoding="utf-8")
    assert mod.main([str(cov), str(thr)]) == 1
