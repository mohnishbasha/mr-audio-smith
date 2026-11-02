"""typer vendors click; importing click directly breaks clean installs (release run for v1.0.0-rc.1)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def regression_cli_never_imports_click_directly() -> None:
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "audio_smith").rglob("*.py")
        if re.search(r"^\s*(import click|from click)", p.read_text(encoding="utf-8"), re.M)
    ]
    assert offenders == []
