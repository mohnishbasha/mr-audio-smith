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

## Sprint 2: Voices and Backends (completed 2026-11-02, tag `sprint-2-complete`)

**Built** (PR #90, issues #20 to #26; follow-up #91): TTSBackend protocol and registry, deterministic
mock backend, license guard, OpenAI-compatible backend with retries, the Maya 2 adapter written against
the verified upstream API (port 8080, `POST /v1/voices` clone registration, `speed` fixed at 1.0 with
post-synthesis `atempo`), Kokoro on CPU, optional Chatterbox, the voice registry with consent records
and clip checks, `voice` and `render` commands, and doctor rows for backends, GPU, and voices.

**Gate evidence:** `render valid.script.md --backend mock` writes chunk audio; the Kokoro integration test
passed locally on CPU; consent is enforced from the CLI (exit 8) and the Python API, and
`require_consent()` re-checks the record and clip hash inside every cloning backend. Maya 2 on a GPU
runner is a manual step (no GPU runner attached).

**Tests added:** about 110 unit, 2 integration (Kokoro, Maya 2 gated on a GPU server).

**What worked:** three agents in parallel against a contract written first (tts/base.py), with the
lead integrating.

**What did not:** the lead stashed the shared working tree while agents were writing, which briefly
removed their files; PR #90 auto-merged with macOS and Windows unit jobs red because only the Ubuntu
unit job was a required check; `setup-ffmpeg` does not support macOS arm64 runners.

**What to change:** other-branch work happens only in a separate `git worktree`; every unit job is now a
required check on `develop`; CI installs ffmpeg with apt, brew, or choco. Promotion to staging is a
fast-forward (squash promotion made the branches diverge).

## Sprint 3: Synthesis and Mastering (completed 2026-11-02, tag `sprint-3-complete`)

**Built** (issues #27 to #37): chunk planner, synthesis runner with per-unit cache, retries, resume, and
bounded concurrency; speaker similarity QA with retakes; assembler; ffmpeg mastering (high-pass,
de-esser, compression, stings, bed ducking, two-pass loudnorm, MP3 and Opus); ID3 tags with same-origin
cover art; waveform peaks; WebVTT captions; manifest and published JSON Schemas; `narrate()` and `run`
with `--approve`, `--dry-run`, and the parent track; a track-level cache.

**Gate evidence:** the fixture letter narrates end to end with the mock backend at -16.4 LUFS; the
reference letter rendered with Kokoro on CPU in 76 s for 4 min 33 s of audio (-16.7 LUFS); unchanged
re-run 0.64 s; loudness, true peak, and caption alignment are covered by automated tests. A cloned-voice
render needs the Maya 2 GPU host and the owner's consented voice (manual), and the listening test needs a
human listener (see docs/LISTENING_TESTS.md).

**Tests added:** about 100 unit, 7 integration (real ffmpeg). Coverage: tts 99, master 99, publish 100,
qa 100 percent.

**What worked:** caching the finished track made NFR-004 trivial; the live-page gate exposed the LLM
blanking the signature, which is now enforced by code.

**What did not:** unit tests that master audio take about a minute in total; resemblyzer needed
`setuptools<81` for `pkg_resources`.

**What to change:** keep heavyweight mastering tests few and focused; consider a short fixture for
pipeline tests.

## Sprints 4 and 5: Publish and Site, Studio (completed 2026-11-02, tags `sprint-4-complete`, `sprint-5-complete`)

Delivered in one PR because the dependency graph runs them in parallel and they share the CLI and API
surface.

**Built** (issues #38 to #49): the `<audio-smith-player>` web component (6.5 KB gzipped, zero
dependencies, axe clean in default and kid variants, works with JavaScript off); embed snippet and player
bundle written on every run with `embed_*` settings; `inject` that splices only between markers and keeps
the rest of the page byte for byte (CRLF preserved, idempotent); translation and language tracks with
alignment checks; `site` batch mode with `--inject-root`; the composite GitHub Action and the
letters-to-a-child example; Studio (FastAPI on 127.0.0.1 with a per-session token and strict CSP, Vite +
Preact UI) for editing chunks, rendering and comparing takes, re-mastering, approving, and injecting with
a diff preview.

**Gate evidence:** Playwright: 14 player specs (keyboard, captions, language toggle, no-JS fallback,
storage blocked, axe) and 5 Studio specs (edit and save marks stale, compare takes and keep the best,
approve persists, inject diff before write, zero external requests) pass locally. Inject verified
idempotent on the reference letter. Site mode skips unchanged pages. The Action is unit-tested with a fake
runner; a run in a throwaway repository is a manual step for the owner (it needs a GPU runner or a server).

**Tests added:** about 120 Python unit, 48 player unit, 23 Studio unit, 19 e2e.

**What worked:** writing the Studio HTTP contract first let the backend and frontend agents build in
parallel and meet on the first try.

**What did not:** several agents edited `cli_commands.py` at the same time; it held only because each
edit was one additive line. Studio media needs the session token, so the UI fetches audio as blobs and the
CSP gained `connect-src blob:`.

**What to change:** give each command group its own module (already true for voice, publish, site,
studio) so parallel work never touches the same file.
