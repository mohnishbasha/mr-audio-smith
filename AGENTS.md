# mr-audio-smith

Turn a web page into a realistic, audience-tuned narration (MP3 + captions + player),
generated locally with pluggable TTS backends (default Maya 2 Native).

## Commands
uv sync --all-extras --dev          # install
make lint                           # ruff + eslint + em dash check
make typecheck                      # mypy --strict + tsc --noEmit
make test                           # unit tests, all packages
make test-int                       # integration (needs ffmpeg, Ollama)
make coverage                       # coverage + thresholds
make smoke                          # end to end with mocks
make e2e                            # Playwright
./scripts/check-versions.sh         # version consistency
uv run python scripts/sync-test-plan.py --add-missing  # TEST_PLAN statuses from real test names
make record-llm                     # re-record LLM fixtures after a writer prompt change (needs Ollama)
uv run mr-audio-smith doctor        # environment check
uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock

## Structure
audio_smith/   core package (api.py is the public surface)
player/        <audio-smith-player> web component
web/studio/    Studio UI
integrations/  pi, goose, opencode, claude-code
docs/          PRD, ARCHITECTURE, DESIGN, SPRINT_PLAN, TEST_PLAN (source of truth)
tests/         unit, integration, smoke, e2e, regression, fixtures

## Code style
Python: mypy --strict, pydantic models, typed errors, pathlib, argument-array subprocess.
TypeScript: strict, no any, no console.log, zero-dependency player.

## Rules
- ALWAYS read the relevant docs/ section before changing behavior.
- ALWAYS write a failing test first.
- ALWAYS update docs/ in the same PR when behavior changes.
- ALWAYS update CHANGELOG.md [Unreleased] for user-facing changes.
- NEVER call the network or a GPU in unit tests.
- NEVER use shell=True or string commands.
- NEVER add em dashes.

## Versioning
pyproject.toml [project].version is the single source of truth. Bump with
scripts/bump-version.sh; verify with scripts/check-versions.sh.

## Boundaries
- NEVER bypass or weaken voice consent checks.
- NEVER commit voice clips, model weights, or generated audio of real people.
- NEVER re-serialize user HTML; inject between markers only.
- NEVER push to main or staging directly.
