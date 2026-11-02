# Sprint retrospectives

## Sprint 0: Scaffold (completed 2026-11-02, tag `sprint-0-complete`)

**Built** (PR #81, issues #1 to #10): spec documents, uv/hatchling project with optional extras
(base install has no torch), typer CLI with `--version` and `doctor`, layered configuration,
typed error hierarchy, ruff + mypy --strict + import-linter + em dash hook, pytest harness with
per-module coverage floors, CI on Ubuntu, macOS, and Windows (Python 3.12 and 3.13), version
scripts, and the agent files (AGENTS, CLAUDE, SKILLS, SOUL, three skills).

**Spec sections updated:** ARCHITECTURE 6.1 (default profile `kid-5`), 6.7 (provider strings kept
in the prompt's format); TEST_PLAN statuses; `docs/BUILD_PROMPT.md` archived.

**Tests added:** 56 unit, 1 integration (clean `uv tool install`), 2 smoke checks.

**Coverage:** 0 to 98 percent (new code).

**What worked:** writing the five spec documents in parallel kept Step 1 short; `scripts/sync-test-plan.py`
made the TEST_PLAN statuses mechanical instead of hand-edited.

**What did not:** two CI failures on the first push: an untracked empty `schemas/` directory broke the
hatchling force-include, and the ruff formatter rewrote the em dash escape sequence into the literal character,
tripping the em dash hook. GitHub also rate-limited the burst of 80 issue creations.

**What to change:** build the em dash from `chr(0x2014)` so no formatter can turn it into a literal;
keep `.gitkeep` files in directories the build references; `create-issues.py` now retries with backoff.
Never switch branches in the shared working tree while agents are writing to it; use a separate
`git worktree` for other-branch operations.

## Sprint 1: Extract and Script (completed 2026-11-02, tag `sprint-1-complete`)

**Built** (PR #83, issues #11 to #19): SSRF-guarded fetcher with IP pinning and per-hop redirect
checks; Block model and FR-003 content hash; extractor honoring every `data-narrate` attribute with
sign-off detection and the opt-in `parent_headings` rule; profile schema, loader, four built-ins, and
JSON Schema; LLM providers (Ollama, Anthropic, OpenAI-compatible, fake replay); Script Markdown
parser, sanitizer, and validator; script writer with one corrective retry; lexicon; content-addressed
cache; `script`, `profile`, and `cache` commands.

**Gate evidence:** `script tests/fixtures/pages/letter-calm.html --llm fake` reproduces the golden
script (a replay of a real qwen3:14b recording). A real run against
https://www.aadhish.us/letter-calm-in-the-chaos.html with `ollama:qwen3:14b` produced 28 chunks and
624 words (target 585, band 468 to 702) with zero violations and the signature exact.

**Spec sections updated:** Prompt amendments (archived in `docs/BUILD_PROMPT.md`), ARCHITECTURE module
map, section 7 cache keys, section 8 `LLMError`, the `maya2` extra; PRD FR-005 length-retry rule;
SPRINT_PLAN spec-change list.

**Tests added:** about 190 unit and 1 integration (Ollama). Coverage of extract, blocks, script,
profiles, and cache is 100 percent.

**What worked:** recording a real model response once and replaying it gives honest golden tests with
no network. Running Ollama against the live page caught a real failure mode.

**What did not:** qwen3:14b on this machine is not deterministic even at temperature 0 with a seed, and
one run blanked the signature chunk on both attempts, failing the gate. Ollama ran the 14B model on
CPU here, so each live call took about 10 minutes. Native Windows needed explicit UTF-8 reads.

**What to change:** verbatim passages and the signature are now enforced by code (`script/verbatim.py`)
instead of being trusted to the model. CI sets `PYTHONUTF8=1`. Always pass `encoding="utf-8"`.
