"""GitHub Action (TEST_PLAN 5.21): changed-file detection, URL mapping, commands, action.yml."""

import importlib.util
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

from audio_smith.paths import safe_slug

ROOT = Path(__file__).resolve().parents[2]
ACTION_DIR = ROOT / "action"
ZERO = "0" * 40


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("narrate_changed", ACTION_DIR / "narrate-changed.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["narrate_changed"] = module
    spec.loader.exec_module(module)
    return module


nc = _load()


class FakeRunner:
    """Records argument lists; answers git and CLI calls from canned data."""

    def __init__(self, diff: str = "", tracked: str = "", help_text: str = "", fail: str = "") -> None:
        self.calls: list[list[str]] = []
        self.diff, self.tracked, self.help_text, self.fail = diff, tracked, help_text, fail

    def __call__(self, argv: Sequence[str]) -> tuple[int, str]:
        self.calls.append(list(argv))
        if argv[:2] == ["git", "diff"]:
            return 0, self.diff
        if argv[:2] == ["git", "ls-files"]:
            return 0, self.tracked
        if "--help" in argv:
            return 0, self.help_text
        if self.fail and self.fail in argv:
            return 1, "boom"
        return 0, ""


def _cfg(**over: str) -> object:
    base = {"pages_glob": "letter-*.html", "site_url": "https://www.aadhish.us", "output_dir": "media/audio"}
    return nc.Config(**{**base, **over})


def test_action_only_files_matching_glob_processed() -> None:
    files = ["letter-a.html", "about.html", "css/letter-b.css", "sub/letter-c.html", "letter-a.html"]
    assert nc.select_pages(files, "letter-*.html") == ["letter-a.html", "sub/letter-c.html"]
    assert nc.select_pages(files, "sub/*.html") == ["sub/letter-c.html"]


def test_action_changed_files_mapped_to_urls() -> None:
    event = {"before": "a" * 40, "after": "b" * 40}
    runner = FakeRunner(diff="letter-a.html\nabout.html\nsub/letter-b.html\n")
    files = nc.changed_files("push", event, runner)
    assert runner.calls == [["git", "diff", "--name-only", "--diff-filter=ACMR", f"{'a' * 40}..{'b' * 40}"]]
    pages = nc.select_pages(files, "letter-*.html")
    assert [nc.page_url("https://www.aadhish.us/", p) for p in pages] == [
        "https://www.aadhish.us/letter-a.html",
        "https://www.aadhish.us/sub/letter-b.html",
    ]


@pytest.mark.parametrize(
    ("name", "event"),
    [
        ("workflow_dispatch", {"before": "a" * 40, "after": "b" * 40}),
        ("push", {"before": ZERO, "after": "b" * 40}),
        ("push", {}),
    ],
)
def test_action_falls_back_to_all_files(name: str, event: dict[str, str]) -> None:
    runner = FakeRunner(tracked="letter-a.html\nletter-b.html\n")
    assert nc.changed_files(name, event, runner) == ["letter-a.html", "letter-b.html"]
    assert runner.calls == [["git", "ls-files"]]


def test_action_command_construction_run_then_inject() -> None:
    cfg = _cfg(profile="kid-5", voice="dad", backend="mock", llm="fake")
    run, inject = nc.build_commands("letter-a.html", cfg, server=False)
    assert run == [
        "mr-audio-smith", "run", "letter-a.html", "--out", "media/audio",
        "--profile", "kid-5", "--voice", "dad", "--backend", "mock", "--llm", "fake",
    ]  # fmt: skip
    assert inject == [
        "mr-audio-smith", "inject", "letter-a.html",
        "--manifest", "media/audio/letter-a/letter-a.manifest.json",
    ]  # fmt: skip


@pytest.mark.parametrize("name", ["letter-a.html", "Letter_Two.HTML", "sub/Letter Three!.html", "x.y.html"])
def test_action_slug_matches_package_slug(name: str) -> None:
    assert nc.slug_for(name) == safe_slug(name)


def test_action_remote_server_url_mode_uses_jobs_api(capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _cfg(server_url="https://gpu.example", server_token="tok")
    without = FakeRunner(help_text="--out --voice")
    nc.process_pages(["letter-a.html"], cfg, without)
    assert not any("--server" in c for c in without.calls)
    assert "S7-T04" in capsys.readouterr().out
    with_flag = FakeRunner(help_text="--server TEXT")
    nc.process_pages(["letter-a.html"], cfg, with_flag)
    run = next(c for c in with_flag.calls if c[:2] == ["mr-audio-smith", "run"] and "--help" not in c)
    assert run[-4:] == ["--server", "https://gpu.example", "--token", "tok"]


def test_action_failed_page_does_not_stop_the_rest() -> None:
    runner = FakeRunner(fail="letter-a.html")
    results = nc.process_pages(["letter-a.html", "letter-b.html"], _cfg(), runner)
    assert [r[1] for r in results] == ["failed", "ok"]


def test_action_commit_message_format_skip_ci() -> None:
    assert nc.commit_message(3) == "chore(audio): narrate 3 pages [skip ci]"


def test_action_no_voice_clips_in_site_repo() -> None:
    specs = nc.pathspecs(_cfg(), ["letter-a.html"])
    assert specs[:2] == ["media/audio", "letter-a.html"]
    assert ":(exclude,glob)**/*.wav" in specs and ":(exclude,glob)**/voices/**" in specs


def test_action_noop_when_nothing_changed(tmp_path: Path) -> None:
    out, summary = tmp_path / "out", tmp_path / "summary.md"
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": "a" * 40, "after": "b" * 40}), encoding="utf-8")
    env = {
        "AS_PAGES_GLOB": "letter-*.html",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
        "RUNNER_TEMP": str(tmp_path),
    }
    runner = FakeRunner(diff="about.html\n")
    assert nc.main(env, runner) == 0
    assert "count=0" in out.read_text(encoding="utf-8")
    assert "no matching pages" in summary.read_text(encoding="utf-8")
    assert all(c[:2] == ["git", "diff"] for c in runner.calls)


def test_action_yml_inputs_and_composite_steps_valid() -> None:
    text = (ACTION_DIR / "action.yml").read_text(encoding="utf-8")
    import yaml

    data = yaml.safe_load(text)
    expected = {
        "pages-glob", "site-url", "profile", "voice", "backend", "llm", "server-url",
        "server-token", "commit", "output-dir", "image-tag", "python-version",
    }  # fmt: skip
    assert set(data["inputs"]) == expected
    assert data["inputs"]["commit"]["default"] == "true"
    assert data["inputs"]["output-dir"]["default"] == "media/audio"
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    assert version is not None and str(data["inputs"]["image-tag"]["default"]) == version.group(1)
    assert data["runs"]["using"] == "composite"
    assert all("shell" in s for s in data["runs"]["steps"] if "run" in s)
    assert "narrate-changed.py" in text and "[skip ci]" in (ACTION_DIR / "narrate-changed.py").read_text(
        "utf-8"
    )
