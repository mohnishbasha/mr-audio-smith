"""Deterministic provider for tests: replay recorded fixtures or a queue of responses."""

import hashlib
from pathlib import Path

from audio_smith.errors import LLMError
from audio_smith.preflight import PreflightIssue

DEFAULT_FIXTURE_DIR = Path("tests/fixtures/llm")
KEY_LEN = 16
KEY_SEPARATOR = "\n\x00\n"


def prompt_key(system: str, user: str) -> str:
    """Stable 16-hex-char key so recordings are found by prompt content."""
    digest = hashlib.sha256((system + KEY_SEPARATOR + user).encode("utf-8")).hexdigest()
    return digest[:KEY_LEN]


class FakeProvider:
    """Replays `{fixture_dir}/{key}.txt`, or pops `responses` in order when given."""

    id = "fake"

    def __init__(self, fixture_dir: Path | None = None, *, responses: list[str] | None = None) -> None:
        self.fixture_dir = fixture_dir if fixture_dir is not None else DEFAULT_FIXTURE_DIR
        self._queue = list(responses) if responses is not None else None
        self.calls: list[tuple[str, str]] = []

    def preflight(self) -> list[PreflightIssue]:
        return []

    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str:
        """Return the next queued response or the recording for this prompt."""
        self.calls.append((system, user))
        if self._queue is not None:
            if not self._queue:
                raise LLMError("FakeProvider response queue is empty")
            return self._queue.pop(0)
        path = self.fixture_dir / f"{prompt_key(system, user)}.txt"
        if not path.is_file():
            raise LLMError(
                f"No recorded LLM response for prompt hash {prompt_key(system, user)}",
                hint=f"Expected {path}. Record it with `make record-llm`.",
            )
        return path.read_text(encoding="utf-8")
