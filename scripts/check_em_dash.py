#!/usr/bin/env python3
"""Fail when any given file contains the em dash character (U+2014).

Used by pre-commit and `make lint`. With no arguments it scans tracked md, py, ts, yaml files.
"""

import subprocess
import sys
from pathlib import Path

EM_DASH = "—"
PATTERNS = ("*.md", "*.py", "*.ts", "*.tsx", "*.yaml", "*.yml")
EXCLUDE = ("docs/BUILD_PROMPT.md",)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *PATTERNS], check=True, capture_output=True, text=True, timeout=30
    )
    return [f for f in out.stdout.splitlines() if f not in EXCLUDE]


def find_em_dashes(paths: list[str]) -> list[str]:
    problems: list[str] = []
    for name in paths:
        path = Path(name)
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if EM_DASH in line:
                problems.append(f"{name}:{lineno}: em dash found; use a comma, colon, or parentheses")
    return problems


def main(argv: list[str]) -> int:
    problems = find_em_dashes(argv or tracked_files())
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
