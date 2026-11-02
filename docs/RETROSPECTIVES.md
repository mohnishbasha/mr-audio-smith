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

## Sprint 6: Release v1.0.0 (2026-11-02, tag `sprint-6-complete`)

**Built** (issues #50 to #55): security review (docs/SECURITY_REVIEW.md) with log redaction, DNS rebinding
and fuzz tests, and a CI security job (pip-audit, npm audit, gitleaks, license check); a generated and
checked THIRD_PARTY_LICENSES.md; the mkdocs-material documentation site with a generated CLI reference and
Python API reference; the release workflow (version verification, CI, build with the Studio and player
bundles inside the wheel, CycloneDX SBOMs, GitHub Release, and PyPI/npm publishing gated on owner setup);
docs/LISTENING_TESTS.md with the protocol and automated pre-checks.

**Decisions:** the `chatterbox` extra was removed because its upstream pins carried about 80 advisories;
torch moved to 2.15; `mutagen` (GPL-2.0-or-later) was replaced by ffmpeg metadata writing so the MIT core
links no copyleft library. pip-audit now reports only setuptools, held below 81 for resemblyzer and not
reachable.

**Gate status, stated plainly:**
- Release checklist: v1.0.0 is versioned, tagged on `main`, and released on GitHub with artifacts and SBOMs.
- PyPI and npm with provenance: **not done**. Publishing needs the owner to configure trusted publishing
  (PyPI) and an npm token, then set `PYPI_PUBLISH` and `NPM_PUBLISH` repository variables and re-run the
  release workflow for the tag.
- Docs site live: the workflow deploys to GitHub Pages on `main`; the custom domain needs DNS by the owner.
- Reference site narrated with v1.0.0: the build agent narrated the reference letter with Kokoro; the
  flagship narration in the parent's cloned voice needs the Maya 2 GPU host and the owner's consented voice.
- Listening tests: **pending the owner** (docs/LISTENING_TESTS.md). The agent never fills in human scores.

**What worked:** splitting security and docs across agents while the lead built the release pipeline.

**What did not:** dependency advisories piled up inside an optional extra nobody needed by default.

**What to change:** run `pip-audit` on every dependency bump (the CI security job now does).

## Sprint 7: Server and MCP (2026-11-02, tag `sprint-7-complete`)

**Built** (issues #56 to #59): `audio_smith/jobs.py` (SQLite job store that survives restarts, one asyncio
worker running the sync pipeline in a thread); the REST API from ARCHITECTURE with bearer tokens (required
off loopback), per-token rate limits, `/healthz` and `/readyz`, and problem+json; the MCP server with the
eight Appendix E tools over stdio and streamable HTTP, each stating the consent rule; remote mode for `run`
and `site` (`--server`, `--token`) that downloads the artifacts and injects locally.

**Gate evidence:** remote mode is tested end to end against a real local `serve` process (uvicorn in a
thread) and a local web server; the MCP stdio integration test narrates the fixture with mocks. A laptop
narrating through the GPU box and Claude Code driving the tools interactively are owner steps.

**What worked:** the server and MCP agents built in parallel with the lead adding remote mode afterwards.

**What did not:** the installed MCP SDK is 2.x, where FastMCP no longer exists; the `mcp` extra now pins
`mcp>=2.3,<3`. Catalog helpers ended up implemented twice (server and MCP); merge them in a follow-up.

## Sprint 8: Harness Integrations (2026-11-02, tag `sprint-8-complete`)

**Built** (issues #60 to #64): the Pi extension on the real `@earendil-works/pi-coding-agent` API (TypeBox
tools mirroring MCP, `/narrate`, `/voices`, `/audio-status`, streaming progress, a session-start context
message); Goose `toolkit.yaml`; the OpenCode config; Claude Code MCP setup and the `narrate-page` skill;
harness smoke tests that launch each config's exact command and complete the MCP handshake; a CI job for
staging and release; docs/guide/agents.md.

**Gate evidence:** every harness config lists all eight tools over stdio; Pi unit tests (13) pass with a
mocked server. Recorded sessions inside each harness are manual (the harness binaries are not installed
here).

## Sprint 9: Packaging (2026-11-02, tag `sprint-9-complete`)

**Built** (issues #65 to #68): CPU, CUDA, and Maya 2 Dockerfiles; local and production Compose files (Caddy
TLS, internal network, read-only root filesystems); the Helm chart with a GPU Maya 2 StatefulSet, optional
Ollama or vLLM, NetworkPolicy, HPA, and ingress, with k3s GPU and kind CPU values; release jobs for
multi-arch images, cosign keyless signing, and the OCI chart (gated on `IMAGES_PUBLISH`).

**Gate evidence:** the CPU image is 0.46 GB compressed and 1.4 GB unpacked after replacing Debian's ffmpeg
with a static build, dropping the `qa` extra from the CPU image, and stripping shared libraries; inside it,
with a read-only root filesystem, the fixture narrates end to end at -16.4 LUFS and `doctor` is green.
`helm lint` and `helm template` pass for all three values files. Not verified here: CUDA and Maya 2 image
builds, a GPU Compose run, a Helm install on the GPU cluster, `ct install` in kind (the helm workflow runs
it), and publishing and signing (gated on owner setup for GHCR).

**What to change:** pin the Maya 2 weights revision and the production image digests before a real deploy.
