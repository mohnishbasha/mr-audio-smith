"""Shared fixtures: every test runs with an isolated environment and working directory."""

from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    import os

    for key in list(os.environ):
        if key.startswith("AUDIO_SMITH_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AUDIO_SMITH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("AUDIO_SMITH_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.chdir(tmp_path)
    yield


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
