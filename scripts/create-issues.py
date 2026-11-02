#!/usr/bin/env python3
"""Create one GitHub issue per task in docs/SPRINT_PLAN.md.

Parses the fixed task format (### SN-Tnn: Title plus bullet fields), creates issues with
labels and milestones through the gh CLI, optionally adds them to the project board, and
finally rewrites task-id dependencies (S2-T03) into issue references (#23).

Usage:
    python scripts/create-issues.py --dry-run
    python scripts/create-issues.py [--project 1] [--owner mohnishbasha]
    python scripts/create-issues.py --project-only --project 1   # add existing issues to board
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PLAN = Path(__file__).resolve().parent.parent / "docs" / "SPRINT_PLAN.md"
TASK_RE = re.compile(r"^### (S\d-T\d\d|OOS-\d\d): (.+)$")
FIELD_RE = re.compile(r"^- \*\*(.+?):\*\*\s*(.*)$")
TASK_ID_RE = re.compile(r"\bS\d-T\d\d\b")
GH_TIMEOUT_S = 60
GH_RETRIES = 5
GH_BACKOFF_S = 30
MILESTONES = {
    "0": "Sprint 0: Scaffold",
    "1": "Sprint 1: Extract and Script",
    "2": "Sprint 2: Voices and Backends",
    "3": "Sprint 3: Synthesis and Mastering",
    "4": "Sprint 4: Publish and Site",
    "5": "Sprint 5: Studio",
    "6": "Sprint 6: Release v1.0.0",
    "7": "Sprint 7: Server and MCP",
    "8": "Sprint 8: Harness Integrations",
    "9": "Sprint 9: Packaging",
}


@dataclass
class Task:
    task_id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    acceptance: list[str] = field(default_factory=list)

    @property
    def labels(self) -> list[str]:
        return [x.strip() for x in self.fields.get("Labels", "").split(",") if x.strip()]

    @property
    def sprint(self) -> str | None:
        m = re.match(r"S(\d)-", self.task_id)
        return m.group(1) if m else None

    def body(self, deps: str) -> str:
        acc = "\n".join(self.acceptance) or "- [ ] See docs/SPRINT_PLAN.md"
        return (
            f"### Task ID\n\n{self.task_id}\n\n"
            f"### Description\n\n{self.fields.get('Description', '')}\n\n"
            f"### Acceptance criteria\n\n{acc}\n\n"
            f"### Spec references\n\n{self.fields.get('Spec refs', 'none')}\n\n"
            f"### Depends on\n\n{deps}\n\n"
            f"### Test scenarios (TEST_PLAN ids)\n\n{self.fields.get('Tests', 'none')}\n"
        )


def parse(text: str) -> list[Task]:
    tasks: list[Task] = []
    current: Task | None = None
    in_acc = False
    for line in text.splitlines():
        m = TASK_RE.match(line)
        if m:
            current = Task(m.group(1), m.group(2).strip())
            tasks.append(current)
            in_acc = False
            continue
        if current is None:
            continue
        if line.startswith("## ") or (line.startswith("### ") and not TASK_RE.match(line)):
            current, in_acc = None, False
            continue
        f = FIELD_RE.match(line)
        if f:
            current.fields[f.group(1)] = f.group(2).strip()
            in_acc = f.group(1) == "Acceptance criteria"
            continue
        if in_acc and line.strip().startswith("- ["):
            current.acceptance.append(line.strip())
    return tasks


def gh(args: list[str]) -> str:
    """Run gh, retrying with backoff because GitHub rate-limits bursts of issue creation."""
    for attempt in range(GH_RETRIES):
        out = subprocess.run(["gh", *args], check=False, capture_output=True, text=True, timeout=GH_TIMEOUT_S)
        if out.returncode == 0:
            return out.stdout.strip()
        print(f"gh failed (attempt {attempt + 1}): {out.stderr.strip()[:200]}", file=sys.stderr)
        time.sleep(GH_BACKOFF_S * (attempt + 1))
    raise RuntimeError(f"gh {' '.join(args[:2])} failed after {GH_RETRIES} attempts")


def existing_issues() -> dict[str, int]:
    raw = gh(["issue", "list", "--state", "all", "--limit", "500", "--json", "number,title"])
    found: dict[str, int] = {}
    for item in json.loads(raw):
        m = re.match(r"^\[(S\d-T\d\d|OOS-\d\d)\]", item["title"])
        if m:
            found[m.group(1)] = item["number"]
    return found


def create(tasks: list[Task], dry_run: bool) -> dict[str, int]:
    numbers = {} if dry_run else existing_issues()
    for t in tasks:
        title = f"[{t.task_id}] {t.title}"
        if t.task_id in numbers:
            print(f"skip (exists #{numbers[t.task_id]}): {title}")
            continue
        args = ["issue", "create", "--title", title, "--body", t.body(t.fields.get("Depends on", "none"))]
        for label in t.labels:
            args += ["--label", label]
        if t.sprint is not None:
            args += ["--milestone", MILESTONES[t.sprint]]
        if dry_run:
            print(f"would create: {title}  labels={t.labels}")
            continue
        url = gh(args)
        numbers[t.task_id] = int(url.rsplit("/", 1)[1])
        print(f"created #{numbers[t.task_id]}: {title}")
    return numbers


def link_dependencies(tasks: list[Task], numbers: dict[str, int]) -> None:
    for t in tasks:
        deps = t.fields.get("Depends on", "none")
        linked = TASK_ID_RE.sub(
            lambda m: f"#{numbers[m.group(0)]}" if m.group(0) in numbers else m.group(0), deps
        )
        if linked != deps and t.task_id in numbers:
            gh(["issue", "edit", str(numbers[t.task_id]), "--body", t.body(f"{linked} ({deps})")])


def add_to_project(numbers: dict[str, int], owner: str, project: int, repo: str) -> None:
    for task_id, num in sorted(numbers.items()):
        gh(
            [
                "project",
                "item-add",
                str(project),
                "--owner",
                owner,
                "--url",
                f"https://github.com/{repo}/issues/{num}",
            ]
        )
        print(f"board: {task_id} #{num}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--project", type=int)
    p.add_argument("--owner", default="mohnishbasha")
    p.add_argument("--repo", default="mohnishbasha/mr-audio-smith")
    p.add_argument("--project-only", action="store_true")
    a = p.parse_args()
    tasks = parse(PLAN.read_text(encoding="utf-8"))
    print(f"parsed {len(tasks)} tasks")
    if a.project_only:
        if a.project is None:
            p.error("--project-only needs --project")
        add_to_project(existing_issues(), a.owner, a.project, a.repo)
        return 0
    numbers = create(tasks, a.dry_run)
    if a.dry_run:
        return 0
    link_dependencies(tasks, numbers)
    if a.project is not None:
        add_to_project(numbers, a.owner, a.project, a.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
