"""Pronunciation lexicon (FR-007): applied to synthesis text only, never to the stored script."""

import re
from pathlib import Path
from typing import Any

import yaml

from audio_smith.errors import UsageError

PROJECT_LEXICON = "lexicon.yaml"


def load_project_lexicon(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise UsageError(f"Invalid lexicon {path}: {e}") from e
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise UsageError(f"Lexicon {path} must map words to respellings", hint="Example: Aadi: AH-dee")
    return dict(data)


def merge(profile_lexicon: dict[str, str], project_lexicon: dict[str, str]) -> dict[str, str]:
    """Union of both; the project file wins on conflicts because it is closest to the content."""
    return {**profile_lexicon, **project_lexicon}


def apply(text: str, lexicon: dict[str, str]) -> str:
    """Whole-word, case-sensitive replacement; longer keys first so phrases beat single words."""
    if not lexicon:
        return text
    keys = sorted(lexicon, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w-])")
    return pattern.sub(lambda m: lexicon[m.group(1)], text)
