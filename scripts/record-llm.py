#!/usr/bin/env python3
"""Record real LLM responses for the fixture pages so FakeProvider can replay them in unit tests.

Runs the script writer against each fixture page with a real provider (default
ollama:qwen3:14b), saving every raw response as tests/fixtures/llm/{prompt_key}.txt. Re-run
whenever the writer prompt template version changes, then review the diff (Appendix J).

Usage: uv run python scripts/record-llm.py [--llm ollama:qwen3:14b] [--profile kid-5]
"""

import argparse
from pathlib import Path

from audio_smith.config import load_settings
from audio_smith.extract import extract
from audio_smith.llm import get_provider, provider_label
from audio_smith.llm.base import LLMProvider
from audio_smith.llm.fake import prompt_key
from audio_smith.profiles import get_profile
from audio_smith.script.markdown import ScriptMeta, serialize
from audio_smith.script.writer import write_script

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
PAGES = {"letter-calm": "https://www.aadhish.us/letter-calm-in-the-chaos.html"}


class Recorder:
    """Wraps a provider and stores each raw response under its prompt key."""

    def __init__(self, inner: LLMProvider, out: Path) -> None:
        self.inner, self.out, self.id = inner, out, f"recorder({inner.id})"

    def preflight(self):  # type: ignore[no-untyped-def]  # delegation only
        return self.inner.preflight()

    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str:
        raw = self.inner.complete(system, user, temperature=temperature, seed=seed, max_tokens=max_tokens)
        (self.out / f"{prompt_key(system, user)}.txt").write_text(raw, encoding="utf-8")
        print(f"recorded {prompt_key(system, user)}")
        return raw


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--llm", default="ollama:qwen3:14b")
    p.add_argument("--profile", default="kid-5")
    a = p.parse_args()
    settings = load_settings()
    recorder = Recorder(get_provider(a.llm, settings), FIXTURES / "llm")
    profile = get_profile(a.profile)
    for slug, url in PAGES.items():
        doc = extract((FIXTURES / "pages" / f"{slug}.html").read_text(encoding="utf-8"), url)
        meta = ScriptMeta(source=url, profile=profile.ref, lang="en", content_hash="recorded",
                          generated_by=provider_label(a.llm))  # fmt: skip
        script, warnings = write_script(doc, profile, recorder, meta)
        print(serialize(script))
        for w in warnings:
            print(f"warning: {w}")


if __name__ == "__main__":
    main()
