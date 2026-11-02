# Skills

| Skill | Directory | When to use |
|---|---|---|
| run-tests | .agent/skills/run-tests | After any code change; before opening a PR |
| check-types | .agent/skills/check-types | After changing signatures or models |
| narrate-fixture | .agent/skills/narrate-fixture | To verify the end-to-end pipeline with mocks |

## Skill format
Each skill is a directory with SKILL.md (frontmatter: name, description; body: when to use,
steps, expected output) and run.sh (executable, exits non-zero on failure).

## Adding a skill
Create .agent/skills/<name>/SKILL.md and run.sh, add a row above, and reference it in
AGENTS.md if it is part of the PR checklist.

## Pi
Pi loads .agent/skills automatically when the repository is opened; skills must not require
interactive input.
