import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_licenses", ROOT / "scripts" / "check-licenses.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FILE_TEXT = """# Third-party licenses

## Python runtime dependencies

| Package | Version | License | URL |
|---|---|---|---|
| httpx | 0.28.1 | BSD-3-Clause | https://x |

## npm packages

| Package | Version | License | URL |
|---|---|---|---|
| preact | 10.29.8 | MIT | https://y |

## Model weights (downloaded at runtime, never bundled)

hand written
"""


def _pip(*rows: tuple[str, str, str]) -> str:
    return json.dumps([{"Name": n, "Version": v, "License": lic, "URL": "https://u"} for n, v, lic in rows])


def test_licenses_parse_pip_filters_to_runtime_and_normalizes() -> None:
    text = _pip(
        ("Jinja2", "3.1", "BSD License"),
        ("pytest", "8", "MIT"),
        ("big", "1", "MIT License\n\nCopyright..." * 9),
    )
    pkgs = mod.parse_pip_licenses(text, {"jinja2", "big"})
    assert [(p.name, p.license) for p in pkgs] == [("big", "MIT License"), ("Jinja2", "BSD License")]
    assert all(p.name != "pytest" for p in pkgs)


def test_licenses_normalize_license_cases() -> None:
    assert mod.normalize_license("") == "UNKNOWN"
    assert mod.normalize_license("MIT | Apache") == "MIT / Apache"
    assert mod.normalize_license("x" * 200) == "UNKNOWN"
    assert mod.normalize_license("MIT License\n\nCopyright (c) 2025") == "MIT License"


def test_licenses_override_applies_only_to_unknown_metadata() -> None:
    pkgs = mod.parse_pip_licenses(_pip(("espeakng_loader", "0.2.4", "UNKNOWN")), None)
    assert pkgs[0].license.startswith("MIT (loader)")
    kept = mod.parse_pip_licenses(_pip(("espeakng_loader", "0.2.4", "Apache-2.0")), None)
    assert kept[0].license == "Apache-2.0"


def test_licenses_parse_license_checker_drops_own_packages() -> None:
    text = json.dumps(
        {
            "@mr-audio-smith/player@0.0.1": {"licenses": "MIT"},
            "@scope/pkg@1.2.3": {"licenses": ["MIT", "ISC"], "repository": "https://r"},
        }
    )
    pkgs = mod.parse_license_checker(text)
    assert [(p.name, p.version, p.license, p.url) for p in pkgs] == [
        ("@scope/pkg", "1.2.3", "MIT, ISC", "https://r")
    ]


def test_licenses_new_dependency_without_entry_fails() -> None:
    py = [mod.Package("httpx", "0.28.1", "BSD-3-Clause", "u"), mod.Package("newdep", "1.0", "MIT", "u")]
    problems = mod.check(FILE_TEXT, py, [mod.Package("preact", "10.29.8", "MIT", "u")])
    assert problems == ["python: newdep 1.0 has no entry in THIRD_PARTY_LICENSES.md"]


def test_licenses_unknown_license_fails_even_with_entry() -> None:
    problems = mod.check(FILE_TEXT, [mod.Package("httpx", "1", "UNKNOWN", "u")], [])
    assert len(problems) == 1 and "unknown license" in problems[0]


def test_licenses_denylist_blocks_agpl_and_gpl3_but_not_lgpl_or_gpl2() -> None:
    for denied in ("AGPL-3.0-only", "GNU Affero General Public License v3", "GPL-3.0-only", "GPLv3+"):
        assert mod.is_denied(denied), denied
    for fine in (
        "LGPL-3.0-or-later",
        "GPL-2.0-or-later",
        "MIT",
        "GNU Library or Lesser General Public License (LGPL)",
    ):
        assert not mod.is_denied(fine), fine


def test_licenses_allowlisted_package_passes_denylist() -> None:
    documented = {"pykakasi", "other"}
    ok = mod.find_problems([mod.Package("pykakasi", "2", "GPLv3+", "u")], documented, "python")
    bad = mod.find_problems([mod.Package("other", "2", "GPLv3+", "u")], documented, "python")
    assert ok == [] and len(bad) == 1 and "denied license" in bad[0]


def test_licenses_replace_section_preserves_hand_written_sections() -> None:
    out = mod.generate(FILE_TEXT, [mod.Package("a", "1", "MIT", "u")], [mod.Package("b", "2", "ISC", "u")])
    assert "| a | 1 | MIT | u |" in out and "httpx" not in out
    assert "| b | 2 | ISC | u |" in out and "preact" not in out
    assert out.endswith("hand written\n")
    assert out.count("## Model weights") == 1
    assert mod.section_names(out, mod.PY_HEADING) == {"a"}


def test_licenses_npm_ls_fallback_reads_manifest(tmp_path: Path) -> None:
    pkg = tmp_path / "node_modules" / "left-pad"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(json.dumps({"license": "WTFPL", "repository": {"url": "git://r"}}))
    found: dict[str, str] = {}
    mod.collect_ls_packages({"dependencies": {"left-pad": {"version": "1.0.0", "dependencies": {}}}}, found)
    assert found == {"left-pad": "1.0.0"}
    row = mod.package_from_manifest(tmp_path, "left-pad", "1.0.0")
    assert (row.license, row.url) == ("WTFPL", "git://r")
    assert mod.package_from_manifest(tmp_path, "missing", "1").license == "UNKNOWN"


def test_licenses_committed_file_has_required_sections() -> None:
    text = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    for heading in (mod.PY_HEADING, mod.NPM_HEADING, "## Model weights", "## Bundled assets"):
        assert heading in text
    assert "Apache-2.0" in text and "maya-research/maya2-native" in text
