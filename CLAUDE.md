@import AGENTS.md

## Memory model
- Product behavior: docs/PRD.md
- Structure and contracts: docs/ARCHITECTURE.md
- Visual rules: docs/DESIGN.md
- What to build next: docs/SPRINT_PLAN.md and the GitHub milestone
- How to test: docs/TEST_PLAN.md

## Key entry points
| Directory | Purpose |
|---|---|
| audio_smith/api.py | Public pipeline API |
| audio_smith/tts/ | Backends (maya2.py is the default) |
| audio_smith/script/ | Script writing and validation |
| audio_smith/master/ | ffmpeg mastering |
| audio_smith/publish/ | Manifest, VTT, embed, inject |
| player/src/ | Web component |

## Before writing any code
1. Find the issue and its acceptance criteria.
2. Read the referenced PRD and ARCHITECTURE sections.
3. Add TEST_PLAN scenarios.
4. Write the failing test.

## PR checklist
make lint && make typecheck && make test && make coverage && ./scripts/check-versions.sh

## Claude-specific rules
- Prefer editing adapters over interfaces.
- When the Maya 2 API differs from ARCHITECTURE, update ARCHITECTURE in the same PR.
- Ask before adding a new runtime dependency.
