import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    "pyproject.toml",
    "player/package.json",
    "integrations/pi/package.json",
    "web/studio/package.json",
    "charts/mr-audio-smith/Chart.yaml",
    "action/action.yml",
    "scripts/check-versions.sh",
    "scripts/extract-changelog.sh",
]

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("yq") is None, reason="needs jq and yq"
)


def _repo(tmp_path: Path) -> Path:
    for rel in FILES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_scripts_check_versions_consistent_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    r = subprocess.run(
        ["bash", "scripts/check-versions.sh"], cwd=repo, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, r.stdout


def test_versions_check_ignores_chart_version_but_checks_app_version(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    chart = repo / "charts/mr-audio-smith/Chart.yaml"
    text = chart.read_text(encoding="utf-8")
    chart.write_text(text.replace("version: 0.1.0", "version: 7.7.7", 1))
    ok = subprocess.run(
        ["bash", "scripts/check-versions.sh"], cwd=repo, capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0, ok.stdout
    chart.write_text(text.replace("appVersion: ", "appVersion: 9.9.9-x", 1))
    bad = subprocess.run(
        ["bash", "scripts/check-versions.sh"], cwd=repo, capture_output=True, text=True, check=False
    )
    assert bad.returncode == 1
    assert "appVersion" in bad.stdout


def test_versions_check_exits_1_naming_mismatched_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    pkg = repo / "web/studio/package.json"
    pkg.write_text(pkg.read_text(encoding="utf-8").replace('"version": "', '"version": "9.9.9-x', 1))
    r = subprocess.run(
        ["bash", "scripts/check-versions.sh"], cwd=repo, capture_output=True, text=True, check=False
    )
    assert r.returncode == 1
    assert "web/studio/package.json" in r.stdout


def test_versions_extract_changelog_prints_only_section(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n## [Unreleased]\n- u\n## [0.1.0] - 2026-11-08\n### Added\n- first\n"
        "## [0.0.1] - 2026-11-01\n- old\n"
    )
    r = subprocess.run(
        ["bash", "scripts/extract-changelog.sh", "0.1.0"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "first" in r.stdout
    assert "old" not in r.stdout
    assert "u\n" not in r.stdout
