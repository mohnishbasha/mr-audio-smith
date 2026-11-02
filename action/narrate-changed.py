"""Narrate the pages a push changed, then embed the player (FR-025).

Runs inside the composite action with inputs passed as environment variables, so no input
value is ever interpolated into a shell string. Everything that touches the outside world
(git, the mr-audio-smith CLI) goes through an injected runner so the logic is unit-tested
without git, a GPU, or a network.
"""

import fnmatch
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ZERO_SHA = "0" * 40
CLI = "mr-audio-smith"
SLUG_MAX = 80
SLUG_BAD = re.compile(r"[^a-z0-9-]+")
REMOTE_NOTE = "remote mode arrives with S7-T04 (--server); narrating on this runner instead"
COMMIT_TEMPLATE = "chore(audio): narrate {n} pages [skip ci]"
NEVER_COMMIT = (":(exclude,glob)**/*.wav", ":(exclude,glob)**/*.flac", ":(exclude,glob)**/voices/**")

Runner = Callable[[Sequence[str]], tuple[int, str]]


@dataclass(frozen=True)
class Config:
    """Action inputs, read once from the environment."""

    pages_glob: str
    site_url: str
    output_dir: str
    profile: str = ""
    voice: str = ""
    backend: str = ""
    llm: str = ""
    server_url: str = ""
    server_token: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Config":
        return cls(
            pages_glob=env.get("AS_PAGES_GLOB", "*.html"),
            site_url=env.get("AS_SITE_URL", ""),
            output_dir=env.get("AS_OUTPUT_DIR", "media/audio"),
            profile=env.get("AS_PROFILE", ""),
            voice=env.get("AS_VOICE", ""),
            backend=env.get("AS_BACKEND", ""),
            llm=env.get("AS_LLM", ""),
            server_url=env.get("AS_SERVER_URL", ""),
            server_token=env.get("AS_SERVER_TOKEN", ""),
        )


def subprocess_runner(argv: Sequence[str]) -> tuple[int, str]:
    """Run an argument list (never a shell string) and return (exit code, combined output)."""
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False)  # noqa: S603
    return proc.returncode, proc.stdout + proc.stderr


def slug_for(path: str) -> str:
    """Mirror of audio_smith.paths.safe_slug for a repo file path (pinned by a unit test)."""
    stem = Path(path).stem or "page"
    slug = SLUG_BAD.sub("-", stem.lower()).strip("-")[:SLUG_MAX].strip("-")
    return slug or "page"


def matches_glob(path: str, pattern: str) -> bool:
    """Match the repo-relative path, or just the file name when the pattern has no slash."""
    target = path if "/" in pattern else Path(path).name
    return fnmatch.fnmatch(target, pattern)


def all_tracked(runner: Runner) -> list[str]:
    code, out = runner(["git", "ls-files"])
    return out.splitlines() if code == 0 else []


def changed_files(event_name: str, event: Mapping[str, object], runner: Runner) -> list[str]:
    """Files changed by the push, or every tracked file for manual runs and first pushes.

    Falls back to everything when the range cannot be diffed (shallow clone, force push), because
    narrating too much is cheap (the cache skips unchanged pages) while missing a page is not.
    """
    before, after = str(event.get("before") or ""), str(event.get("after") or "")
    if event_name == "workflow_dispatch" or not before or before == ZERO_SHA or not after:
        return all_tracked(runner)
    code, out = runner(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{before}..{after}"])
    return out.splitlines() if code == 0 else all_tracked(runner)


def select_pages(files: Sequence[str], pattern: str) -> list[str]:
    return [f for f in dict.fromkeys(files) if matches_glob(f, pattern)]


def page_url(site_url: str, path: str) -> str:
    return f"{site_url.rstrip('/')}/{path.lstrip('/')}" if site_url else path


def manifest_path(output_dir: str, page: str) -> str:
    slug = slug_for(page)
    return f"{output_dir.rstrip('/')}/{slug}/{slug}.manifest.json"


def supports_server(runner: Runner) -> bool:
    code, out = runner([CLI, "run", "--help"])
    return code == 0 and "--server" in out


def build_commands(page: str, cfg: Config, *, server: bool) -> list[list[str]]:
    """The two CLI invocations for one page: run, then inject (no combined flag exists yet)."""
    run = [CLI, "run", page, "--out", cfg.output_dir]
    for flag, value in (
        ("--profile", cfg.profile),
        ("--voice", cfg.voice),
        ("--backend", cfg.backend),
        ("--llm", cfg.llm),
    ):
        if value:
            run += [flag, value]
    if server and cfg.server_url:
        run += ["--server", cfg.server_url]
        if cfg.server_token:
            run += ["--token", cfg.server_token]
    inject = [CLI, "inject", page, "--manifest", manifest_path(cfg.output_dir, page)]
    return [run, inject]


def commit_message(n: int) -> str:
    return COMMIT_TEMPLATE.format(n=n)


def pathspecs(cfg: Config, pages: Sequence[str]) -> list[str]:
    """What the commit step may stage: outputs and edited pages, never voice clips."""
    return [cfg.output_dir, *pages, *NEVER_COMMIT]


def process_pages(pages: Sequence[str], cfg: Config, runner: Runner) -> list[tuple[str, str, str]]:
    """Run every page; returns (page, status, detail). One failure does not stop the rest."""
    server = False
    if cfg.server_url:
        server = supports_server(runner)
        print("using remote server" if server else f"server-url set: {REMOTE_NOTE}")
    results: list[tuple[str, str, str]] = []
    for page in pages:
        status, detail = "ok", ""
        for argv in build_commands(page, cfg, server=server):
            code, out = runner(argv)
            if code != 0:
                status, detail = "failed", (out.strip().splitlines() or ["error"])[-1]
                break
        results.append((page, status, detail))
    return results


def summary_markdown(cfg: Config, results: Sequence[tuple[str, str, str]]) -> str:
    lines = ["## mr-audio-smith", "", "| page | url | status |", "|---|---|---|"]
    for page, status, detail in results:
        lines.append(f"| {page} | {page_url(cfg.site_url, page)} | {status} {detail}".rstrip() + " |")
    if not results:
        lines.append("| (no matching pages changed) | | |")
    return "\n".join(lines) + "\n"


def write_outputs(path: str | None, values: Mapping[str, str]) -> None:
    if path:
        with Path(path).open("a", encoding="utf-8") as fh:
            for key, value in values.items():
                fh.write(f"{key}={value}\n")


def load_event(env: Mapping[str, str]) -> Mapping[str, object]:
    path = env.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main(env: Mapping[str, str] | None = None, runner: Runner = subprocess_runner) -> int:
    env = os.environ if env is None else env
    cfg = Config.from_env(env)
    if cfg.server_token:
        print(f"::add-mask::{cfg.server_token}")
    files = changed_files(env.get("GITHUB_EVENT_NAME", ""), load_event(env), runner)
    pages = select_pages(files, cfg.pages_glob)
    results = process_pages(pages, cfg, runner)
    summary = summary_markdown(cfg, results)
    if env.get("GITHUB_STEP_SUMMARY"):
        with Path(env["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write(summary)
    done = [p for p, status, _ in results if status == "ok"]
    list_file = Path(env.get("RUNNER_TEMP", ".")) / "audio-smith-paths.txt"
    list_file.write_text("\n".join(pathspecs(cfg, done)) + "\n", encoding="utf-8")
    write_outputs(
        env.get("GITHUB_OUTPUT"),
        {"count": str(len(done)), "message": commit_message(len(done)), "paths-file": str(list_file)},
    )
    return 1 if any(status == "failed" for _, status, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
