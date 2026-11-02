#!/usr/bin/env python3
"""Enforce per-module coverage floors from .coverage-thresholds.toml against coverage.json.

Usage: python scripts/check-coverage.py [coverage.json] [.coverage-thresholds.toml]
Python thresholds are checked against coverage.py JSON output (line coverage, aggregated per
file or directory prefix). TypeScript thresholds are enforced by vitest configs.
"""

import json
import sys
import tomllib
from pathlib import Path


def aggregate(files: dict[str, dict[str, dict[str, int]]], prefix: str) -> float | None:
    covered = total = 0
    for name, data in files.items():
        norm = name.replace("\\", "/")
        if norm == prefix or norm.startswith(prefix.rstrip("/") + "/"):
            covered += data["summary"]["covered_lines"]
            total += data["summary"]["num_statements"]
    if total == 0:
        return None
    return 100.0 * covered / total


def check(coverage: dict[str, object], thresholds: dict[str, object]) -> list[str]:
    files = coverage["files"]  # type: ignore[index]
    totals = coverage["totals"]  # type: ignore[index]
    failures: list[str] = []
    for key, target in thresholds.items():
        if key == "overall":
            actual: float | None = float(totals["percent_covered"])
        else:
            actual = aggregate(files, key)
        if actual is None:
            print(f"skip  {key}: no measured code yet")
            continue
        status = "ok  " if actual >= float(target) else "FAIL"  # type: ignore[arg-type]
        print(f"{status}  {key}: {actual:.1f}% (target {target}%)")
        if status == "FAIL":
            failures.append(key)
    return failures


def main(argv: list[str]) -> int:
    cov_path = Path(argv[0] if argv else "coverage.json")
    thr_path = Path(argv[1] if len(argv) > 1 else ".coverage-thresholds.toml")
    coverage = json.loads(cov_path.read_text(encoding="utf-8"))
    thresholds = tomllib.loads(thr_path.read_text(encoding="utf-8"))["python"]
    failures = check(coverage, thresholds)
    if failures:
        print(f"coverage below threshold: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
