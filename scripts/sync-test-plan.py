#!/usr/bin/env python3
"""Keep docs/TEST_PLAN.md honest: mark scenario rows Automated when a test with that id exists.

Test ids are function names in tests/ (Python, TypeScript `test("id"` / `it("id"`) and
`echo "smoke_..."` markers in tests/smoke/*.sh. Rows already marked Skipped are left alone.
With --add-missing, automated tests that have no row are appended to section 5.28.
Exit code 1 with --check when any row would change (used in CI).
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "TEST_PLAN.md"
PY_DEF = re.compile(r"^\s*(?:async\s+)?def ((?:test|it|smoke|e2e|regression)_\w+)\(", re.M)
TS_DEF = re.compile(r"""\b(?:test|it)\(\s*["'`]((?:test|e2e|it|regression)_\w+)""")
SMOKE = re.compile(r'echo "((?:smoke)_\w+)"')
ROW = re.compile(r"^\| `?([a-z0-9_]+)`? \|(.*)\| ⚠️ Deferred \|\s*$")
EXTRA_HEADER = "### 5.28 Additional automated scenarios"
TS_GLOBS = ("player/tests", "web/studio/src", "web/studio/tests", "integrations/pi/tests", "tests/e2e")


def collect_ids() -> set[str]:
    ids: set[str] = set()
    for f in (ROOT / "tests").rglob("*.py"):
        ids |= set(PY_DEF.findall(f.read_text(encoding="utf-8")))
    for f in (ROOT / "tests" / "smoke").glob("*.sh"):
        ids |= set(SMOKE.findall(f.read_text(encoding="utf-8")))
    for g in TS_GLOBS:
        base = ROOT / g
        if base.exists():
            for f in base.rglob("*.ts"):
                if "node_modules" not in f.parts:
                    ids |= set(TS_DEF.findall(f.read_text(encoding="utf-8")))
    return ids


def sync(text: str, ids: set[str], add_missing: bool) -> tuple[str, int, list[str]]:
    lines = text.splitlines()
    changed = 0
    planned: set[str] = set()
    for i, line in enumerate(lines):
        m = re.match(r"^\| `?([a-z0-9_]+)`? \|", line)
        if m:
            planned.add(m.group(1))
        r = ROW.match(line)
        if r and r.group(1) in ids:
            lines[i] = line.replace("| ⚠️ Deferred |", "| ✅ Automated |")
            changed += 1
    missing = sorted(ids - planned)
    if add_missing and missing:
        if EXTRA_HEADER not in text:
            idx = next(i for i, ln in enumerate(lines) if ln.startswith("## 6."))
            block = [EXTRA_HEADER, "", "| ID | Scenario | Type | Status |", "|---|---|---|---|", ""]
            lines[idx:idx] = block
        idx = lines.index(EXTRA_HEADER) + 4
        while idx < len(lines) and lines[idx].startswith("|"):
            idx += 1
        for name in missing:
            kind = name.split("_", 1)[0]
            kind = {"test": "Unit", "it": "Integration", "smoke": "Smoke", "e2e": "E2E"}.get(
                kind, "Regression"
            )
            lines.insert(
                idx, f"| `{name}` | {name.split('_', 1)[1].replace('_', ' ')} | {kind} | ✅ Automated |"
            )
            idx += 1
            changed += 1
    return "\n".join(lines) + "\n", changed, missing


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--add-missing", action="store_true")
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    text = PLAN.read_text(encoding="utf-8")
    new, changed, missing = sync(text, collect_ids(), a.add_missing)
    if a.check:
        if new != text:
            print(f"TEST_PLAN.md out of date ({changed} rows); run scripts/sync-test-plan.py --add-missing")
            return 1
        return 0
    PLAN.write_text(new, encoding="utf-8")
    print(f"updated {changed} rows; {len(missing)} tests without a planned row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
