# mr-audio-smith Sprint Plan

This plan lists every sprint (0 to 9) and every task of the mr-audio-smith build. It is the input to `scripts/create-issues.py`, which parses the task blocks below into GitHub issues, so the task format is fixed and must not be reformatted.

## How to read this plan

### Estimate legend

| Size | Effort |
|---|---|
| S | half a day |
| M | 1 day |
| L | 2 days |
| XL | 3 or more days; split into smaller tasks before starting |

No task in this plan is XL. If a task grows past L during implementation, stop and split it into two issues before continuing.

### Delivery process (ADR-018)

One feature branch and one pull request per sprint (`feature/sprint-N-<slug>`), closing all of that sprint's issues, instead of one PR per task. This is because a single autonomous agent executes the plan. Test-driven development, the spec protocol (read the PRD and ARCHITECTURE references on each task before coding), and per-issue implementation comments still apply to every issue. Each sprint ends at a hard-stop gate: the gate checklist must be fully checked before the next sprint starts.

### Task format

Each task is a `### SN-Tnn: Title` heading followed by Labels, Estimate, Spec refs, Description, Acceptance criteria, Tests, and Depends on. Spec refs name PRD functional or non-functional requirement ids (FR, NFR) and ARCHITECTURE decision ids (ADR) or sections. Tests name TEST_PLAN ids following the convention below.

```
Unit:        test_{module}_{function}_{scenario}_{expected_outcome}
Integration: it_{component}_{operation}_{scenario}
Smoke:       smoke_{feature}_{minimal_assertion}
E2E:         e2e_{user_story_id}_{scenario}
Regression:  regression_{gh_issue_number}_{what_was_broken}
```

Items that cannot be completed by the executing agent (GPU-runner Maya 2 integration, human listening tests, publishing to PyPI, npm, or GHCR which needs trusted-publisher setup by the owner, and DNS for getaudiosmith.com) are marked in the acceptance criteria as manual or deferred steps and are recorded honestly in TEST_PLAN as skipped or deferred.

## Sprint overview

| Sprint | Name | Duration | Goal | Release |
|---|---|---|---|---|
| 0 | Scaffold | 1 week | Tooling, CI, agent files, doctor, config | |
| 1 | Extract and Script | 1 week | Fetch, extract, profiles, LLM providers, script writer + validator | 0.1.0 |
| 2 | Voices and Backends | 1 week | TTSBackend, Maya 2, Kokoro, OpenAI, mock, consent | 0.2.0 |
| 3 | Synthesis and Mastering | 2 weeks | Chunks, QA, mastering, cache, manifest, VTT, `run` (the product) | 0.3.0 |
| 4 | Publish and Site | 1 week | Player, embed, inject, translation, site mode, Action | 0.4.0 |
| 5 | Studio | 1 week | Local review UI | 0.5.0 |
| 6 | Release | 1 week | Hardening, docs, listening tests, PyPI + npm | **1.0.0** |
| 7 | Server and MCP | 1 week | REST jobs, MCP tools, remote mode | 1.1.0-rc |
| 8 | Harness Integrations | 1 week | Pi, Goose, OpenCode, Claude Code | 1.1.0-rc |
| 9 | Packaging | 1 week | Docker, Compose, Helm, signing | **1.1.0** |

Total: 11 weeks.

## Dependency graph

```
S0 Scaffold -> S1 Extract+Script -> S2 Voices -> S3 Synthesis+Mastering (core)
                                                     |
                                    S4 Publish+Site <+> S5 Studio
                                                     |
                                                 S6 Release v1.0.0
                                                     |
                                    S7 Server+MCP -> S8 Harnesses -> S9 Packaging
```

Sprint 6 dependencies on "S5 complete" are expressed at task level as S5-T05. Sprint 7 tasks that depend on "Sprint 6" list S6-T06. Sprint 8 and Sprint 9 tasks that depend on "Sprint 7" list S7-T04.

## Milestones

Milestones are created by Step 2.5 of the build prompt. Adjust due dates to the actual start date; keep the relative durations (Sprint 3 is two weeks).

| Milestone | Description | Due |
|---|---|---|
| Sprint 0: Scaffold | Tooling, CI, agent files, empty CLI, spec docs committed | 2026-11-09 |
| Sprint 1: Extract and Script | Fetch, extract, profiles, LLM providers, script writer+validator | 2026-11-16 |
| Sprint 2: Voices and Backends | TTSBackend, Maya 2, Kokoro, OpenAI, mock, voice registry+consent | 2026-11-23 |
| Sprint 3: Synthesis and Mastering | Chunked synthesis, QA, mastering, cache, manifest, VTT, run cmd | 2026-12-07 |
| Sprint 4: Publish and Site | Player, embed, inject, translation, site batch, GitHub Action | 2026-12-14 |
| Sprint 5: Studio | Local review UI: edit script, render chunks, compare takes | 2026-12-21 |
| Sprint 6: Release v1.0.0 | Docs, hardening, listening tests, PyPI + npm, v1.0.0 | 2026-12-28 |
| Sprint 7: Server and MCP | REST server with jobs, MCP server (stdio + HTTP) | 2027-01-04 |
| Sprint 8: Harness Integrations | Pi extension, Goose toolkit, OpenCode, Claude Code skill | 2027-01-11 |
| Sprint 9: Packaging | Docker (CUDA, CPU, arm64), Compose, Helm, cosign | 2027-01-18 |

(All due at 23:59:59Z on the date shown.)

## Spec changes recorded against the source prompt

- Maya 2 server default port is 8080, not 8000: `AUDIO_SMITH_MAYA2_URL` defaults to `http://127.0.0.1:8080/v1` (verified against the upstream `maya3.server`). The Compose health check and service URLs in Sprint 9 use 8080 accordingly.
- Maya 2 requires `speed=1.0` on the server; speaking rate is applied after synthesis with ffmpeg `atempo` (ADR-016).
- Speaker similarity uses resemblyzer in the `qa` extra, lazy-imported, skipped with a manifest warning when absent (ADR-015).
- Kokoro requires Python below 3.13 upstream, so the `kokoro` extra carries a `python_version < "3.13"` marker and doctor hints to use 3.12 (ADR-017).
- Forced alignment for word-level captions is deferred (see OOS-04).

---

## Sprint 0: Scaffold

**Milestone:** Sprint 0: Scaffold
**Duration:** 1 week
**Goal:** A repository where `mr-audio-smith --version` and `mr-audio-smith doctor` run, CI is green on all platforms, every agent file exists, and nothing product-specific is implemented yet.

### S0-T01: Commit the five spec documents
- **Labels:** type: spec, area: ci, priority: p0, size: L, sprint: 0
- **Estimate:** L
- **Spec refs:** PRD (all sections), ARCHITECTURE ADR-018
- **Description:** Generate PRD, ARCHITECTURE, DESIGN, SPRINT_PLAN, TEST_PLAN per Step 1. This task is completed before Step 2 and recorded retroactively as an issue.
- **Acceptance criteria:**
  - [ ] All five files exist under `docs/` with every required section
  - [ ] Every FR has acceptance criteria; every US maps to at least one FR
  - [ ] Committed as the first commit on `main`
  - [ ] No em dash character (U+2014) appears in any committed file
- **Tests:** none
- **Depends on:** none

### S0-T02: Python project skeleton with uv
- **Labels:** type: chore, area: cli, priority: p0, size: M, sprint: 0
- **Estimate:** M
- **Spec refs:** PRD NFR-001, ARCHITECTURE ADR-017
- **Description:** Create `pyproject.toml` (hatchling build backend, Python `>=3.12,<3.14`), `uv.lock`, `audio_smith/` package with `__init__.py` reading version via `importlib.metadata`, typer CLI with `--version`. Optional dependency groups: `maya2`, `kokoro` (marked `python_version < "3.13"` per ADR-017), `chatterbox`, `cloud`, `server`, `mcp`, `qa`, `dev`.
- **Acceptance criteria:**
  - [ ] `uv sync --all-extras --dev` succeeds on macOS arm64 and Linux x86_64
  - [ ] `uv run mr-audio-smith --version` prints the version from `pyproject.toml`
  - [ ] Base install (no extras) does not pull torch
- **Tests:** test_cli_version_prints_pyproject_version, smoke_cli_version_exits_zero
- **Depends on:** S0-T01

### S0-T03: Repository hygiene files
- **Labels:** type: chore, area: ci, priority: p0, size: S, sprint: 0
- **Estimate:** S
- **Spec refs:** PRD NFR-009, ARCHITECTURE ADR-018
- **Description:** Create `.gitignore`, `.editorconfig`, `.gitattributes` (mark `*.wav *.mp3 *.opus` as binary, LFS for `tests/fixtures/voices/*.wav` and `assets/stings/*`), `LICENSE` (MIT, Serverless Ventures LLC, 2026), `THIRD_PARTY_LICENSES.md` stub, `CHANGELOG.md` with `[Unreleased]`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` (with DCO sign-off requirement). The `.gitignore` must include these groups. Python: `__pycache__/`, `*.py[cod]`, `.venv/`, `dist/`, `build/`, `*.egg-info/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`. TypeScript, Node, Bun: `node_modules/`, `*.tsbuildinfo`, `player/dist/`, `web/studio/dist/`, `integrations/pi/dist/`, `.bun/`. Environment: `.env`, `.env.*`, `!.env.*.example`. Test and coverage: `coverage/`, `.coverage`, `htmlcov/`, `coverage.xml`, `playwright-report/`, `test-results/`. Product runtime: `.audio-smith/cache/`, `out/`, `audio/`, `*.db`, `*.db-shm`, `*.db-wal`, `voices/*/reference.wav` (never commit real voice clips by default) with the exception `!tests/fixtures/voices/*.wav`. Model weights: `models/`, `*.safetensors`, `*.bin`, `*.gguf`. Agent sessions: `.pi/sessions/`, `.agent/sessions/`, `CLAUDE.local.md`. OS and editor: `.DS_Store`, `Thumbs.db`, `.vscode/settings.json`, `.idea/`. Lock files ARE tracked: `uv.lock`, `bun.lockb`, `package-lock.json`.
- **Acceptance criteria:**
  - [ ] All files present; `voices/*/reference.wav` ignored; fixtures not ignored
  - [ ] `git check-ignore` confirms `voices/dad/reference.wav` is ignored and `tests/fixtures/voices/clean.wav` is not
  - [ ] LICENSE names Serverless Ventures LLC and year 2026
- **Tests:** none
- **Depends on:** S0-T02

### S0-T04: Lint, format, type-check toolchain
- **Labels:** type: chore, area: ci, priority: p0, size: S, sprint: 0
- **Estimate:** S
- **Spec refs:** PRD NFR-009
- **Description:** ruff (lint + format) with rules `E,F,W,I,N,UP,B,A,C4,SIM,RUF,S,PTH,TID,PL`, mypy `--strict`, pre-commit hooks (ruff, mypy, codespell, check-yaml, end-of-file-fixer, a custom hook rejecting em dash characters in `*.md *.py *.ts *.yaml`). `Makefile` targets: `lint`, `format`, `typecheck`, `test`, `test-int`, `coverage`, `smoke`, `e2e`, `check-versions`, `build`.
- **Acceptance criteria:**
  - [ ] `make lint typecheck` exit 0 on the skeleton
  - [ ] The em dash hook fails on a file containing the character U+2014
  - [ ] Every listed Makefile target exists
- **Tests:** test_emdash_hook_file_with_emdash_fails
- **Depends on:** S0-T02

### S0-T05: Test harness and coverage thresholds
- **Labels:** type: test, area: ci, priority: p0, size: M, sprint: 0
- **Estimate:** M
- **Spec refs:** PRD NFR-009, TEST_PLAN strategy
- **Description:** pytest with `pytest-cov`, `pytest-asyncio`, `pytest-timeout`, `hypothesis`, `respx` (httpx mocking), `syrupy` (snapshots). Markers: `integration`, `gpu`, `slow`. Create `tests/{unit,integration,smoke,e2e,regression}/` and `tests/fixtures/` with the fixtures listed in TEST_PLAN (pages, scripts, profiles, voices, recorded LLM responses). `.coverage-thresholds.toml` and `scripts/check-coverage.py` that fails CI when any module is under threshold.
- **Acceptance criteria:**
  - [ ] `make test` runs and reports coverage per package
  - [ ] Threshold script fails when a module falls under its target
  - [ ] All fixture files listed in TEST_PLAN exist
- **Tests:** test_check_coverage_module_under_threshold_fails
- **Depends on:** S0-T04

### S0-T06: CI workflow
- **Labels:** type: chore, area: ci, priority: p0, size: M, sprint: 0
- **Estimate:** M
- **Spec refs:** PRD NFR-009, ARCHITECTURE ADR-018
- **Description:** `.github/workflows/ci.yml` with jobs: `lint-and-typecheck` (ubuntu, macos, windows), `unit-tests` (matrix 3 OS x Python 3.12, 3.13), `coverage` (ubuntu, upload to Codecov), `integration-tests` (ubuntu, installs ffmpeg, Ollama with `qwen3:0.6b`, Kokoro CPU), `e2e-tests` (ubuntu, Playwright), `check-versions`, `smoke`. `gpu-integration` job runs only on `workflow_dispatch` and on PRs to `staging`/`main` against a self-hosted runner labeled `gpu` with Maya 2.
- **Acceptance criteria:**
  - [ ] All jobs green on the skeleton
  - [ ] Concurrency group cancels superseded runs
  - [ ] Dependabot configured for pip (uv), npm, github-actions, docker
  - [ ] `gpu-integration` is skipped (not failed) when no `gpu` runner is registered; registering the runner is a manual owner step
- **Tests:** none
- **Depends on:** S0-T05

### S0-T07: Version scripts
- **Labels:** type: chore, area: ci, priority: p1, size: S, sprint: 0
- **Estimate:** S
- **Spec refs:** PRD NFR-010, ARCHITECTURE Versioning section
- **Description:** `scripts/check-versions.sh`, `scripts/extract-changelog.sh`, `scripts/bump-version.sh` exactly as specified in the Versioning section.
- **Acceptance criteria:**
  - [ ] `check-versions.sh` exits 1 naming the file when a version differs
  - [ ] `extract-changelog.sh 0.1.0` prints only that section
  - [ ] `bump-version.sh` updates every version-bearing file in one run
- **Tests:** test_check_versions_mismatch_names_file, test_extract_changelog_version_prints_only_section
- **Depends on:** S0-T02

### S0-T08: Agent repository files
- **Labels:** type: docs, area: harness, priority: p0, size: M, sprint: 0
- **Estimate:** M
- **Spec refs:** PRD FR-024, ARCHITECTURE agent files section
- **Description:** Create `AGENTS.md`, `CLAUDE.md`, `SKILLS.md`, `SOUL.md`, `.agent/skills/run-tests/{SKILL.md,run.sh}`, `.agent/skills/check-types/{SKILL.md,run.sh}`, `.agent/skills/narrate-fixture/{SKILL.md,run.sh}` with the content specified in Appendix K.
- **Acceptance criteria:**
  - [ ] `CLAUDE.md` first line is `@import AGENTS.md`
  - [ ] Both required skills run and exit 0 on the skeleton
  - [ ] SOUL.md has at least 6 hard constraints and no commands or paths
- **Tests:** test_agent_files_claude_md_first_line_imports_agents, test_agent_files_soul_md_has_six_constraints
- **Depends on:** S0-T04, S0-T05

### S0-T09: Doctor command (skeleton)
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 0
- **Estimate:** M
- **Spec refs:** PRD FR-020, NFR-001
- **Description:** `doctor.py` with a check registry; implement Python version, ffmpeg presence and version (>= 6.0), disk space, cache dir writable. Later sprints register backend, LLM, GPU, voice checks.
- **Acceptance criteria:**
  - [ ] Human table output and `--json` output
  - [ ] Exit 3 when a required check fails; every failure has a hint
  - [ ] Check registry accepts registrations from other modules without editing `doctor.py`
- **Tests:** test_doctor_run_required_check_fails_exit_3, test_doctor_json_output_validates, test_doctor_failure_has_hint
- **Depends on:** S0-T02

### S0-T10: Config system
- **Labels:** type: feature, area: cli, priority: p1, size: S, sprint: 0
- **Estimate:** S
- **Spec refs:** PRD FR-021, ARCHITECTURE configuration precedence
- **Description:** pydantic-settings `Settings` with env prefix `AUDIO_SMITH_`, project file `audio-smith.toml` discovered upward from cwd, CLI flags override env override file override defaults. Document precedence in ARCHITECTURE.
- **Acceptance criteria:**
  - [ ] Precedence covered by unit tests
  - [ ] Unknown keys in `audio-smith.toml` produce a warning, not a crash
  - [ ] `AUDIO_SMITH_MAYA2_URL` defaults to `http://127.0.0.1:8080/v1`
- **Tests:** test_config_load_cli_overrides_env_overrides_file, test_config_load_unknown_key_warns_not_crashes, test_config_discover_toml_found_in_parent_dir
- **Depends on:** S0-T02

### Sprint 0 Gate
Hard stop. Sprint 1 does not start until every item is checked.
- [ ] Spec docs committed and current
- [ ] `make lint typecheck test smoke` green locally
- [ ] CI green on ubuntu, macos, windows
- [ ] `mr-audio-smith --version` and `doctor` work from a clean `uv tool install .`
- [ ] All agent files present and validated
- [ ] `check-versions.sh` passes
- [ ] Retrospective written, `sprint-0-complete` tagged

---

## Sprint 1: Extract and Script

**Milestone:** Sprint 1: Extract and Script
**Duration:** 1 week
**Goal:** `mr-audio-smith script <url>` produces a validated, kid-tuned Script Markdown file for the reference letter, using a local LLM, with no audio yet.

### S1-T01: Safe fetcher
- **Labels:** type: feature, area: fetch, priority: p0, size: M, sprint: 1
- **Estimate:** M
- **Spec refs:** PRD FR-001, NFR-005
- **Description:** httpx client with timeout, max bytes (streamed, abort over limit), redirect limit 5, scheme allowlist (`http`, `https`, `file` for local paths), SSRF guard resolving DNS and rejecting private, loopback, link-local, and metadata ranges unless `--allow-private`. Respect `Content-Type` and charset.
- **Acceptance criteria:**
  - [ ] FR-001 ACs met
  - [ ] `test_fetch_private_ip_blocked` and the redirect-to-private case are covered
  - [ ] Responses over the byte limit abort mid-stream with a clear error
- **Tests:** test_fetch_private_ip_blocked, test_fetch_redirect_to_private_blocked, test_fetch_over_max_bytes_aborts, test_fetch_scheme_ftp_rejected
- **Depends on:** S0-T10

### S1-T02: Block model and normalization
- **Labels:** type: feature, area: extract, priority: p0, size: S, sprint: 1
- **Estimate:** S
- **Spec refs:** PRD FR-003
- **Description:** pydantic `Block`, `BlockDoc`; normalization (Unicode NFC, collapse whitespace, smart quotes to straight quotes for hashing only, strip emoji via the `emoji` package plus regional indicator ranges); `content_hash()` per FR-003.
- **Acceptance criteria:**
  - [ ] FR-003 ACs met
  - [ ] Property tests with hypothesis for whitespace invariance
- **Tests:** test_blocks_hash_whitespace_change_stable, test_blocks_hash_text_change_differs, test_extract_blocks_emoji_stripped
- **Depends on:** S0-T05

### S1-T03: Extractor
- **Labels:** type: feature, area: extract, priority: p0, size: L, sprint: 1
- **Estimate:** L
- **Spec refs:** PRD FR-002, NFR-005
- **Description:** selectolax-based DOM walk implementing FR-002 order and rules. Map `h1` to title, `h2-h4` to heading, `p` to paragraph, `ol/ul > li` to list_item (index and nested heading captured), `blockquote` to quote, elements with `data-narrate-role="signature"` or a final short paragraph after the last heading starting with a sign-off pattern to signature. Remove nav, header, footer, aside, form, script, style, noscript, svg, button elements. Labels like "Something Dad believes" and "A grown-up note" are treated as headings; "A grown-up note" content goes to parent track only when marked `data-narrate="parent"` (no magic string matching in core; provide an opt-in profile rule `parent_headings: ["A grown-up note"]`).
- **Acceptance criteria:**
  - [ ] FR-002 ACs met
  - [ ] Snapshot test on `letter-calm.html` matches expected block JSON
  - [ ] `hostile.html` handled within limits
- **Tests:** test_extract_blocks_data_narrate_present_uses_only_marked_element, test_extract_blocks_skip_attribute_excluded, test_extract_blocks_parent_attribute_routed, test_extract_blocks_letter_calm_snapshot, test_extract_blocks_hostile_html_within_limits
- **Depends on:** S1-T02

### S1-T04: Profile schema, loader, built-ins
- **Labels:** type: feature, area: profiles, priority: p0, size: M, sprint: 1
- **Estimate:** M
- **Spec refs:** PRD FR-004, ARCHITECTURE profile format
- **Description:** pydantic schema for Profile YAML (ARCHITECTURE format); loader with precedence (project `./profiles` over built-in); built-ins `kid-5`, `kid-8`, `adult-commute`, `adult-brief`; `profile list|show|validate` commands; export JSON Schema to `schemas/profile.schema.json`.
- **Acceptance criteria:**
  - [ ] FR-004 ACs met
  - [ ] Invalid profiles produce errors naming the field path
  - [ ] A project profile of the same id overrides the built-in
- **Tests:** test_profiles_load_invalid_rate_rejected, test_profiles_load_project_overrides_builtin, test_profiles_schema_export_matches_checked_in
- **Depends on:** S0-T10

### S1-T05: LLM provider interface and providers
- **Labels:** type: feature, area: llm, priority: p0, size: L, sprint: 1
- **Estimate:** L
- **Spec refs:** PRD FR-005, NFR-005
- **Description:** `LLMProvider` protocol; `OllamaProvider` (REST `/api/chat`, not subprocess), `AnthropicProvider` (official SDK, model configurable), `OpenAICompatProvider` (base_url + key), `FakeProvider` (replays recorded fixtures by prompt hash). Preflight checks register with doctor. Provider string format `ollama:qwen3:14b`, `anthropic:<model-id>`, `openai_compat:<base_url>#<model>`.
- **Acceptance criteria:**
  - [ ] Each provider unit-tested with respx
  - [ ] Ollama integration test with a tiny model
  - [ ] Provider strings parse for all three formats and reject malformed input
- **Tests:** test_llm_ollama_chat_success_returns_text, test_llm_anthropic_chat_success_returns_text, test_llm_openai_compat_chat_success_returns_text, test_llm_fake_replays_by_prompt_hash, test_llm_provider_string_malformed_rejected, it_ollama_chat_tiny_model_returns_text
- **Depends on:** S0-T09

### S1-T06: Script writer
- **Labels:** type: feature, area: script, priority: p0, size: L, sprint: 1
- **Estimate:** L
- **Spec refs:** PRD FR-005, FR-006
- **Description:** Build system prompt from profile (`writing` and `speech` sections) and a fixed rule block: output Script Markdown only, chunk numbering, allowed markers only, keep `{verbatim}` blocks exact, keep signature exact, no emoji, no markdown other than chunk headers, explain big words inline, spoken transitions for list items, add `interactive_moments` count of participatory lines, target length `target_minutes * 130 * rate` words. User prompt carries block JSON. Store prompt template in `audio_smith/script/prompts/writer.md` with a version number included in the script cache key.
- **Acceptance criteria:**
  - [ ] FR-005 ACs met
  - [ ] With FakeProvider the reference letter yields the golden script
  - [ ] Changing the prompt template version changes the script cache key
- **Tests:** test_script_writer_letter_calm_fake_matches_golden, test_script_writer_prompt_version_in_cache_key, it_ollama_script_kid5_within_length
- **Depends on:** S1-T03, S1-T04, S1-T05

### S1-T07: Script Markdown parser, serializer, validator
- **Labels:** type: feature, area: script, priority: p0, size: M, sprint: 1
- **Estimate:** M
- **Spec refs:** PRD FR-006
- **Description:** Parse frontmatter and chunks, round-trip serialize, validate per FR-006, corrective retry loop in writer.
- **Acceptance criteria:**
  - [ ] FR-006 ACs met
  - [ ] Round-trip property test
  - [ ] The corrective retry feeds the violation list back to the LLM exactly once
- **Tests:** test_script_validate_unknown_marker_rejected, test_script_validate_verbatim_chunk_changed_rejected, test_script_writer_retry_with_violations_succeeds, test_script_roundtrip_parse_serialize_identity
- **Depends on:** S1-T06

### S1-T08: Lexicon
- **Labels:** type: feature, area: script, priority: p2, size: S, sprint: 1
- **Estimate:** S
- **Spec refs:** PRD FR-007
- **Description:** Merge profile lexicon with project `lexicon.yaml`; apply at synthesis time only.
- **Acceptance criteria:**
  - [ ] FR-007 ACs met
  - [ ] Whole-word matching only ("Aadi" replaced, "Aadish" not)
- **Tests:** test_lexicon_apply_whole_word_only, test_lexicon_merge_project_overrides_profile
- **Depends on:** S1-T04

### S1-T09: `script` command
- **Labels:** type: feature, area: cli, priority: p0, size: S, sprint: 1
- **Estimate:** S
- **Spec refs:** PRD FR-005, NFR-003, FR-012
- **Description:** Wire stages 1 and 2 with cache for blocks and scripts; `--force` bypasses cache; writes `{slug}.blocks.json` and `{slug}.en.script.md`. Slug from URL path stem, sanitized.
- **Acceptance criteria:**
  - [ ] Second run on unchanged page is a cache hit under 2 s
  - [ ] `--force` bypasses the cache
  - [ ] Slug is sanitized (no path separators, no leading dots)
- **Tests:** test_cache_unchanged_page_skips_render, smoke_script_fake_llm_writes_script
- **Depends on:** S1-T07

### Sprint 1 Gate
Hard stop. Sprint 2 does not start until every item is checked.
- [ ] `mr-audio-smith script tests/fixtures/pages/letter-calm.html --llm fake` matches golden
- [ ] Real run against the reference URL with Ollama produces a valid kid-5 script within length target
- [ ] Coverage: `extract`, `blocks`, `script`, `profiles` at or above targets
- [ ] ARCHITECTURE data formats match implementation
- [ ] Retrospective written, `sprint-1-complete` tagged

---

## Sprint 2: Voices and Backends

**Milestone:** Sprint 2: Voices and Backends
**Duration:** 1 week
**Goal:** Any validated script chunk can be synthesized by Maya 2 (with a registered cloned voice), Kokoro, OpenAI, or the mock backend through one interface.

### S2-T01: TTSBackend protocol, registry, mock backend
- **Labels:** type: feature, area: tts, priority: p0, size: M, sprint: 2
- **Estimate:** M
- **Spec refs:** PRD FR-009, ARCHITECTURE TTSBackend protocol
- **Description:** `Capabilities`, `SynthParams` (rate, seed, lang, temperature), `PcmAudio` (numpy float32 + sample_rate), backend registry by id, `MockBackend` producing deterministic tones whose duration is proportional to text length and pitch derived from voice id.
- **Acceptance criteria:**
  - [ ] FR-009 ACs met
  - [ ] Mock is deterministic across platforms
- **Tests:** test_tts_mock_synth_same_input_identical_samples, test_tts_registry_unknown_backend_raises, test_tts_mock_duration_proportional_to_text
- **Depends on:** S0-T05

### S2-T02: OpenAI-compatible backend
- **Labels:** type: feature, area: tts, priority: p0, size: M, sprint: 2
- **Estimate:** M
- **Spec refs:** PRD FR-009, ARCHITECTURE ADR-016
- **Description:** One class using the official `openai` SDK `audio.speech.create` with `response_format="wav"`, configurable `base_url`, `model`, `api_key`. Adapter hooks: `map_voice(VoiceRef)`, `map_params(SynthParams)`, `map_text(str)` for markers. Used directly as `openai` (cloud) and `openai_compat`.
- **Acceptance criteria:**
  - [ ] respx-mocked tests for success, 4xx, 5xx with retry, timeout
  - [ ] Adapter hooks are overridable by subclasses without copying the request code
- **Tests:** test_tts_openai_synth_success_returns_pcm, test_tts_openai_synth_4xx_raises_no_retry, test_tts_openai_synth_5xx_retries_then_raises, test_tts_openai_synth_timeout_raises
- **Depends on:** S2-T01

### S2-T03: Maya 2 Native backend
- **Labels:** type: feature, area: tts, priority: p0, size: L, sprint: 2
- **Estimate:** L
- **Spec refs:** PRD FR-010, ARCHITECTURE ADR-016
- **Description:** Adapter over S2-T02 pointed at the local Maya 2 server (`AUDIO_SMITH_MAYA2_URL`, default `http://127.0.0.1:8080/v1`; the upstream server default port is 8080, not 8000). Built-in voice ids pass through. Cloned voices: before the first synthesis the adapter registers the consented clip with `POST /v1/voices` using voice_id `as-{voice_id}-{clip_hash[:8]}` (idempotent, `replace=false`, a 409 or "exists" response is treated as success) and then uses that id as `voice` in `/v1/audio/speech`. The request body is `{"model":"maya3","input","voice","language","response_format":"wav","normalize":true,"seed","temperature"}`; `speed` is always 1.0 because the server requires it, and speaking rate is applied after synthesis with ffmpeg `atempo` (ADR-016). Server 503 responses are retried honoring `retry_after`. Optional `--maya2-mode inproc` loads the model in-process via the Python package when the `maya2` extra is installed (package `maya3`, class `Maya3TTS.from_pretrained("maya-research/maya2-native", max_seats=N)`, `.generate(text, lang, voice)`, `.register_voice(name, ref_audio, ref_text, lang)`). Capabilities: 12 languages (en plus as, bn, gu, hi, kn, ml, mr, or, pa, ta, te), cloning true, 24 kHz, license Apache-2.0, commercial_ok true; 20 built-in voices. Pause markers become separate requests joined by silence (Maya 2 has no inline tags); `*emphasis*` stripped. Maya 2 needs a Linux NVIDIA GPU (about 8 GB VRAM) and has no Apple MPS support.
- **Acceptance criteria:**
  - [ ] FR-010 ACs met (respx-mocked server tests run everywhere)
  - [ ] `it_maya2_synth_clone_returns_24khz_mono` passes on the GPU runner (manual or deferred until a GPU runner is registered; recorded as skipped in TEST_PLAN otherwise)
  - [ ] Doctor reports server reachability (`GET /health`: 503 loading, 200 ready) and loaded model
  - [ ] Clone registration is idempotent across repeated runs
- **Tests:** test_tts_maya2_synth_builtin_voice_passes_through, test_tts_maya2_register_clone_idempotent_on_409, test_tts_maya2_speed_always_one, test_tts_maya2_503_retries_with_retry_after, test_tts_maya2_pause_marker_splits_requests, it_maya2_synth_clone_returns_24khz_mono
- **Depends on:** S2-T02, S2-T05

### S2-T04: Kokoro backend (CPU fallback)
- **Labels:** type: feature, area: tts, priority: p1, size: M, sprint: 2
- **Estimate:** M
- **Spec refs:** PRD FR-009, ARCHITECTURE ADR-017
- **Description:** In-process Kokoro (`kokoro` package, 82M weights, Apache-2.0); English voices; clone false. Downloads weights on first use to `models/` with checksum verification. The `kokoro` extra requires Python below 3.13 (ADR-017); on 3.13 the doctor hints to use Python 3.12.
- **Acceptance criteria:**
  - [ ] Integration test on CPU in CI
  - [ ] Capability flags correct (clone false, English only)
  - [ ] Checksum mismatch on downloaded weights is rejected
- **Tests:** it_kokoro_synth_cpu_returns_audio, test_tts_kokoro_capabilities_clone_false, test_tts_kokoro_weights_checksum_mismatch_rejected
- **Depends on:** S2-T01

### S2-T05: Voice registry, consent, clip check
- **Labels:** type: feature, area: voices, priority: p0, size: L, sprint: 2
- **Estimate:** L
- **Spec refs:** PRD FR-011, NFR-005, ARCHITECTURE voice directory layout
- **Description:** `voice add|list|check|remove` commands; voice directory layout per ARCHITECTURE; consent record required (interactive prompt or flags); clip check per FR-011 using soundfile + numpy (duration, rate, clipping, SNR estimate via noise floor percentile); clip normalized and resampled to 24 kHz mono copy stored as `reference.24k.wav`; voice clip hash computed. Consent enforcement lives in `voices.registry.resolve()` so every front door inherits it.
- **Acceptance criteria:**
  - [ ] FR-011 ACs met
  - [ ] `test_consent_clone_unregistered_voice_raises` passes
  - [ ] Clip check fixtures pass and fail as expected
- **Tests:** test_consent_clone_unregistered_voice_raises, test_clipcheck_too_short_rejected, test_clipcheck_clipped_rejected, test_clipcheck_noisy_rejected, test_clipcheck_clean_accepted, test_voices_add_without_consent_rejected
- **Depends on:** S0-T10

### S2-T06: Backend preflight and doctor integration
- **Labels:** type: feature, area: cli, priority: p1, size: S, sprint: 2
- **Estimate:** S
- **Spec refs:** PRD FR-020
- **Description:** Register per-backend checks (server reachable, model loaded, GPU visible via `torch.cuda.is_available()` when torch installed, weights present), registered voices valid.
- **Acceptance criteria:**
  - [ ] Doctor table shows each backend with status and hint
  - [ ] Missing optional extras are reported as not installed, not as failures
- **Tests:** test_doctor_backend_checks_listed_with_hint, test_doctor_maya2_unreachable_reports_hint
- **Depends on:** S2-T03, S2-T04

### S2-T07: License guard
- **Labels:** type: feature, area: tts, priority: p2, size: S, sprint: 2
- **Estimate:** S
- **Spec refs:** PRD FR-009, NFR-008
- **Description:** If a backend reports `commercial_ok: false`, require `--accept-noncommercial` and record it in the manifest warnings.
- **Acceptance criteria:**
  - [ ] Unit tests for both paths
- **Tests:** test_license_guard_noncommercial_without_flag_raises, test_license_guard_noncommercial_with_flag_records_warning
- **Depends on:** S2-T01

### Sprint 2 Gate
Hard stop. Sprint 3 does not start until every item is checked.
- [ ] `mr-audio-smith render tests/fixtures/scripts/valid.script.md --backend mock` produces WAV chunks
- [ ] Maya 2 renders a chunk in a registered cloned voice on the GPU runner (manual or deferred if no GPU runner exists; record in the retrospective)
- [ ] Kokoro renders a chunk on CPU in CI
- [ ] Consent enforcement verified from CLI and Python API
- [ ] Retrospective written, `sprint-2-complete` tagged

---

## Sprint 3: Synthesis and Mastering (Core Feature)

**Milestone:** Sprint 3: Synthesis and Mastering
**Duration:** 2 weeks
**Goal:** `mr-audio-smith run <url> --profile kid-5 --voice dad` produces a mastered, captioned, cached narration with a manifest. This sprint IS the product.

### S3-T01: Chunk planner
- **Labels:** type: feature, area: tts, priority: p0, size: M, sprint: 3
- **Estimate:** M
- **Spec refs:** PRD FR-012, FR-007
- **Description:** Convert script chunks into synthesis units: split on `[pause N]` markers into segments, enforce backend `max_chars` by sentence-splitting (never mid-sentence), apply lexicon, compute chunk keys.
- **Acceptance criteria:**
  - [ ] Unit tests for split rules, lexicon application, key stability
  - [ ] No unit is ever split mid-sentence
- **Tests:** test_planner_split_on_pause_marker, test_planner_max_chars_splits_at_sentence_boundary, test_planner_chunk_key_stable_across_runs, test_planner_lexicon_applied
- **Depends on:** S2-T01, S1-T08

### S3-T02: Synthesis runner with cache and resume
- **Labels:** type: feature, area: tts, priority: p0, size: L, sprint: 3
- **Estimate:** L
- **Spec refs:** PRD FR-012, NFR-003
- **Description:** Iterate units, cache hits skip, misses synthesize with retries (2, exponential backoff with jitter), write WAV to cache atomically (temp file + rename), progress bar (rich), Ctrl-C safe, `--chunks` subset rendering.
- **Acceptance criteria:**
  - [ ] FR-012 ACs met
  - [ ] Killing mid-run and re-running only renders the remainder
  - [ ] No partially written WAV is ever visible in the cache
- **Tests:** test_cache_unchanged_page_skips_render, test_runner_kill_midrun_resume_renders_remainder, test_runner_cache_write_atomic, test_runner_chunks_subset_only_renders_selected
- **Depends on:** S3-T01

### S3-T03: Speaker similarity QA
- **Labels:** type: feature, area: qa, priority: p1, size: L, sprint: 3
- **Estimate:** L
- **Spec refs:** PRD FR-013, ARCHITECTURE ADR-015
- **Description:** `qa` extra using `resemblyzer` (ADR-015: chosen over SpeechBrain ECAPA; lazy-imported). Embed reference clip once; per chunk compute cosine similarity; if under threshold, re-render with new seed up to `takes_per_chunk` (default 2); keep best; record scores. Skipped gracefully when extra not installed (warning in manifest).
- **Acceptance criteria:**
  - [ ] FR-013 ACs met
  - [ ] Unit tests with stubbed embeddings
  - [ ] Absence of the `qa` extra yields a manifest warning, not an error
- **Tests:** test_qa_similarity_below_threshold_rerenders, test_qa_similarity_keeps_best_take, test_qa_extra_missing_skips_with_warning
- **Depends on:** S3-T02

### S3-T04: Assembler
- **Labels:** type: feature, area: master, priority: p0, size: M, sprint: 3
- **Estimate:** M
- **Spec refs:** PRD FR-014, FR-015
- **Description:** Concatenate segments with silences (pause markers, `pause_after_heading_ms`, `pause_between_chunks_ms`), short crossfade (10 ms) at joins to avoid clicks, resample to 44.1 kHz, track chunk start and end timestamps for VTT.
- **Acceptance criteria:**
  - [ ] Golden test on mock audio: total duration equals sum of parts plus pauses within 5 ms
  - [ ] Chunk start and end timestamps are exposed for VTT generation
- **Tests:** test_assembler_total_duration_equals_parts_plus_pauses, test_assembler_output_rate_44100, test_assembler_timestamps_monotonic
- **Depends on:** S3-T02

### S3-T05: ffmpeg mastering chain
- **Labels:** type: feature, area: master, priority: p0, size: L, sprint: 3
- **Estimate:** L
- **Spec refs:** PRD FR-014, NFR-008, ARCHITECTURE ADR-016
- **Description:** `ffmpeg.py` wrapper using argument arrays. Chain: high-pass 70 Hz, gentle de-esser, light compression, optional intro and outro stings, optional music bed with `sidechaincompress` ducking (bed at -24 dB under voice), two-pass `loudnorm` to I=-16, TP=-1.5, LRA=11, encode MP3 (libmp3lame 128k mono) and optional Opus. Speaking-rate adjustment for Maya 2 uses `atempo` (ADR-016). Ship two original CC0 stings in `assets/stings/` (generated procedurally in a script, documented in THIRD_PARTY_LICENSES as original).
- **Acceptance criteria:**
  - [ ] FR-014 ACs met
  - [ ] `test_master_loudness_within_target` measures output with ffmpeg ebur128
  - [ ] ffmpeg is invoked with argument arrays only, never through a shell string
- **Tests:** test_master_loudness_within_target, test_master_true_peak_below_limit, test_ffmpeg_wrapper_no_shell_invocation, test_master_atempo_rate_changes_duration
- **Depends on:** S3-T04

### S3-T06: ID3 tagging and cover art
- **Labels:** type: feature, area: master, priority: p2, size: S, sprint: 3
- **Estimate:** S
- **Spec refs:** PRD FR-014
- **Description:** mutagen tags: TIT2 title, TPE1 author (from page meta author or config), TALB site name, TDRC date, APIC cover from page `og:image` when same-origin and under 1 MB, else none.
- **Acceptance criteria:**
  - [ ] Tags readable by mutagen in tests
  - [ ] Cross-origin or oversized `og:image` yields no cover
- **Tests:** test_id3_tags_readable_by_mutagen, test_id3_cover_cross_origin_skipped, test_id3_cover_over_1mb_skipped
- **Depends on:** S3-T05

### S3-T07: WebVTT captions
- **Labels:** type: feature, area: publish, priority: p1, size: M, sprint: 3
- **Estimate:** M
- **Spec refs:** PRD FR-015
- **Description:** Sentence-level cues from chunk timestamps; distribute within a chunk by character-length proportion. Refinement with forced alignment is deferred and tracked as enhancement OOS-04.
- **Acceptance criteria:**
  - [ ] FR-015 ACs met on mock audio
  - [ ] Cues align within 150 ms of the true sentence boundaries
- **Tests:** test_vtt_cues_align_within_150ms, test_vtt_output_valid_webvtt_header
- **Depends on:** S3-T04

### S3-T08: Manifest and schemas
- **Labels:** type: feature, area: publish, priority: p0, size: M, sprint: 3
- **Estimate:** M
- **Spec refs:** PRD FR-016, ARCHITECTURE manifest format
- **Description:** Build and write manifest per ARCHITECTURE; publish `schemas/manifest.schema.json`, `schemas/blocks.schema.json`, `schemas/profile.schema.json`; validate in tests.
- **Acceptance criteria:**
  - [ ] FR-016 ACs met
  - [ ] Manifest warnings carry QA skips and non-commercial acceptance
  - [ ] Checked-in schemas match the pydantic models
- **Tests:** test_manifest_build_validates_against_schema, test_manifest_schemas_match_models, test_manifest_records_warnings
- **Depends on:** S3-T05, S3-T07

### S3-T09: `run` and `render` commands end to end
- **Labels:** type: feature, area: cli, priority: p0, size: L, sprint: 3
- **Estimate:** L
- **Spec refs:** PRD FR-026, FR-012, FR-014, FR-016
- **Description:** Wire all stages; `--approve` pauses after script generation, opens the script in `$EDITOR`, then continues; `--dry-run` prints plan and cache status; output layout `out/{slug}/` with all artifacts. Parent track rendered when blocks exist with `track: parent`.
- **Acceptance criteria:**
  - [ ] Smoke test with mocks passes
  - [ ] Real run on the reference letter produces a listenable MP3 in a cloned voice on the GPU runner (manual or deferred without a GPU runner; the listening itself is a human step)
  - [ ] FR-026 ACs met
- **Tests:** smoke_run_mock_outputs_exist, test_run_dry_run_prints_plan_no_writes, test_run_parent_track_rendered_when_blocks_present
- **Depends on:** S3-T03, S3-T06, S3-T08

### S3-T10: Python API
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 3
- **Estimate:** M
- **Spec refs:** PRD FR-026, ARCHITECTURE library-first layering
- **Description:** `audio_smith.narrate(source, profile=..., voice=..., backend=..., langs=..., out=...) -> Manifest` and stage functions (`extract`, `write_script`, `render_script`, `master`, `publish`). CLI becomes a thin layer over the API.
- **Acceptance criteria:**
  - [ ] Documented in README
  - [ ] API used by CLI tests
  - [ ] import-linter contract keeps front-door modules importing only `audio_smith.api` and models
- **Tests:** test_api_narrate_mock_returns_manifest, test_import_linter_frontdoors_use_api_only
- **Depends on:** S3-T09

### S3-T11: Performance pass
- **Labels:** type: perf, area: tts, priority: p2, size: M, sprint: 3
- **Estimate:** M
- **Spec refs:** PRD NFR-003
- **Description:** Measure NFR-003 on the reference letter; enable request concurrency for HTTP backends (bounded semaphore, default 2) since Maya 2 serves concurrent streams; record numbers in `docs/PERFORMANCE.md`.
- **Acceptance criteria:**
  - [ ] NFR-003 met or a tracked issue explains the gap
  - [ ] Concurrency is bounded by a semaphore and configurable
- **Tests:** test_runner_concurrency_bounded_by_semaphore
- **Depends on:** S3-T09

### Sprint 3 Gate
Hard stop. Sprint 4 does not start until every item is checked.
- [ ] Reference letter narrated end to end in a cloned voice, kid-5 profile
- [ ] Loudness, true peak, VTT alignment verified by automated tests
- [ ] Unchanged re-run under 2 seconds
- [ ] Internal listening test (TEST_PLAN protocol) averages 4 or higher (human step; record as deferred if the owner has not yet listened)
- [ ] Coverage at or above targets for `tts`, `master`, `publish`, `qa`
- [ ] Retrospective written, `sprint-3-complete` tagged

---

## Sprint 4: Publish and Site

**Milestone:** Sprint 4: Publish and Site
**Duration:** 1 week
**Goal:** Narrations appear on real pages through a polished player, extra languages work, a whole site can be narrated in one command, and a GitHub Action does it on push.

### S4-T01: `<audio-smith-player>` web component
- **Labels:** type: feature, area: player, priority: p0, size: L, sprint: 4
- **Estimate:** L
- **Spec refs:** PRD NFR-007, NFR-011, FR-017, DESIGN player states
- **Description:** TypeScript, no dependencies, built with `bun build` to ESM and IIFE, published as `@mr-audio-smith/player`. Attributes: `src`, `captions`, `label`, `size` (`default` or `kid`), `tracks` (JSON array of `{lang, label, src, captions}`), `theme` (`auto`, `light`, `dark`). Wraps a slotted native `<audio>` so the page works without JS. Implements DESIGN.md states, keyboard (Space, K play or pause; arrows seek 5 s; C captions; L language), Media Session API metadata, remembers last position per src in localStorage inside try/catch.
- **Acceptance criteria:**
  - [ ] NFR-007 and NFR-011 met
  - [ ] E2E tests for keyboard, captions, language toggle, no-JS fallback
  - [ ] Works when localStorage throws
- **Tests:** e2e_US006_player_keyboard_play_pause, e2e_US012_player_captions_toggle, e2e_US006_player_no_js_fallback_plays, e2e_US006_player_language_toggle_switches_track, e2e_US006_player_storage_blocked_still_plays
- **Depends on:** S0-T06

### S4-T02: Embed snippet generator
- **Labels:** type: feature, area: publish, priority: p0, size: S, sprint: 4
- **Estimate:** S
- **Spec refs:** PRD FR-017
- **Description:** Generate `{slug}.embed.html` per FR-017. Player script reference is configurable: self-hosted path (default `/media/audio/audio-smith-player.js`, copied into the output dir) or jsDelivr URL pinned to the exact version.
- **Acceptance criteria:**
  - [ ] Snippet validates as HTML
  - [ ] Renders correctly with and without JS
  - [ ] jsDelivr mode pins the exact package version
- **Tests:** test_embed_snippet_valid_html, test_embed_jsdelivr_url_pins_exact_version, test_embed_self_hosted_copies_player_script
- **Depends on:** S4-T01, S3-T08

### S4-T03: Inject command
- **Labels:** type: feature, area: publish, priority: p0, size: M, sprint: 4
- **Estimate:** M
- **Spec refs:** PRD FR-018
- **Description:** FR-018 using a parser that preserves original formatting outside markers (string splice on marker offsets, never re-serialize the whole DOM). `--selector` (default `h1`) decides where markers go if absent.
- **Acceptance criteria:**
  - [ ] Idempotence and untouched-outside tests pass
  - [ ] Dry-run diff output
- **Tests:** test_inject_idempotent_second_run_no_diff, test_inject_outside_markers_untouched, test_inject_dry_run_prints_diff_no_write, test_inject_selector_places_markers_when_absent
- **Depends on:** S4-T02

### S4-T04: Translation and language tracks
- **Labels:** type: feature, area: script, priority: p1, size: M, sprint: 4
- **Estimate:** M
- **Spec refs:** PRD FR-008, FR-010
- **Description:** FR-008. Translate validated script per extra language, validate alignment, render each language with the same voice (cross-lingual cloning on Maya 2), manifest lists tracks, embed gets language toggle. Backends lacking a language fail preflight with a clear message.
- **Acceptance criteria:**
  - [ ] Hindi track rendered on GPU runner (manual or deferred without a GPU runner)
  - [ ] Alignment test passes
  - [ ] A backend lacking the requested language fails preflight before any synthesis
- **Tests:** test_translate_preserves_chunk_count_and_pauses, test_translate_backend_lacks_language_fails_preflight, test_manifest_lists_language_tracks
- **Depends on:** S3-T09

### S4-T05: Site batch mode
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 4
- **Estimate:** M
- **Spec refs:** PRD FR-019
- **Description:** FR-019. Parse index page links, filter same-origin plus glob, run sequentially with shared backend session, summary table (page, status cached or rendered or failed, duration). `--inject-root <dir>` maps URLs to local HTML files for injection in a static-site repo.
- **Acceptance criteria:**
  - [ ] Fixture index with 3 pages: second run renders 0
  - [ ] Cross-origin links are excluded
- **Tests:** test_site_index_links_same_origin_filtered, test_site_second_run_renders_zero, test_site_inject_root_maps_urls_to_files
- **Depends on:** S4-T03

### S4-T06: GitHub Action
- **Labels:** type: feature, area: action, priority: p1, size: L, sprint: 4
- **Estimate:** L
- **Spec refs:** PRD FR-025, NFR-005
- **Description:** `action/action.yml` composite action. Inputs: `pages-glob`, `site-url`, `profile`, `voice`, `backend`, `server-url` (use remote `mr-audio-smith serve` instead of local GPU), `server-token`, `commit` (bool), `output-dir`. Steps: detect changed files via `git diff` on the push range, map to URLs, run `site` or remote jobs, inject, commit with message `chore(audio): narrate {n} pages [skip ci]`. Voice clips are never stored in the site repo; with a remote server the voice lives on the server.
- **Acceptance criteria:**
  - [ ] FR-025 ACs met
  - [ ] Example workflow in `examples/static-site/.github/workflows/narrate.yml`
  - [ ] Tested in a throwaway repo via `act` or a test repo
- **Tests:** test_action_yml_inputs_match_spec, smoke_action_changed_files_mapped_to_urls
- **Depends on:** S4-T05

### S4-T07: Example for the reference site
- **Labels:** type: docs, area: publish, priority: p2, size: S, sprint: 4
- **Estimate:** S
- **Spec refs:** PRD FR-019, FR-025
- **Description:** `examples/letters-to-a-child/` with `audio-smith.toml`, `profiles/kid-5.yaml` override, lexicon, data-narrate markup guide for letter templates, and the workflow file.
- **Acceptance criteria:**
  - [ ] Example runs end to end with mock backend in CI
- **Tests:** smoke_example_letters_mock_outputs_exist
- **Depends on:** S4-T06

### Sprint 4 Gate
Hard stop. Sprint 5 does not start until every item is checked.
- [ ] Player passes accessibility checks (axe-core in Playwright) with zero violations
- [ ] Inject verified idempotent on the reference letter fixture
- [ ] Site mode narrates the fixture index incrementally
- [ ] Action runs green in a test repo
- [ ] Retrospective written, `sprint-4-complete` tagged

---

## Sprint 5: Studio

**Milestone:** Sprint 5: Studio
**Duration:** 1 week
**Goal:** Authors review and perfect narrations in a localhost UI before publishing.

### S5-T01: Studio backend routes
- **Labels:** type: feature, area: studio, priority: p0, size: M, sprint: 5
- **Estimate:** M
- **Spec refs:** PRD FR-022, NFR-005
- **Description:** FastAPI app mounted by `mr-audio-smith studio`: list projects in `out/`, get and save script (with validation), render chunk (returns take id), list takes with similarity scores, select take, re-master, approve (writes `approved: true` to manifest). Binds 127.0.0.1; random per-session token in URL to prevent other local sites from calling it (CSRF guard).
- **Acceptance criteria:**
  - [ ] Route tests with httpx TestClient
  - [ ] Token enforced on every route
  - [ ] Server refuses to bind a non-loopback address
- **Tests:** test_studio_routes_missing_token_rejected, test_studio_save_script_invalid_rejected, test_studio_approve_writes_manifest_flag, test_studio_bind_non_loopback_refused
- **Depends on:** S3-T10

### S5-T02: Studio frontend shell
- **Labels:** type: feature, area: studio, priority: p0, size: M, sprint: 5
- **Estimate:** M
- **Spec refs:** PRD FR-022, NFR-005, DESIGN studio wireframes
- **Description:** `web/studio` with Vite + TypeScript + Preact, design tokens from Design System, layout from DESIGN.md wireframes, built assets copied into `audio_smith/studio/static/` at package build.
- **Acceptance criteria:**
  - [ ] No external network requests (verified in e2e via request interception)
  - [ ] Built assets are present in the wheel
- **Tests:** e2e_US017_studio_no_external_requests
- **Depends on:** S5-T01

### S5-T03: Script editor with chunk list
- **Labels:** type: feature, area: studio, priority: p0, size: L, sprint: 5
- **Estimate:** L
- **Spec refs:** PRD FR-022, FR-006
- **Description:** Chunk list with status (cached, stale, rendering, failed), inline editor per chunk with marker autocomplete for `[pause N]`, live validation errors, save marks edited chunks stale.
- **Acceptance criteria:**
  - [ ] E2E for edit, validate, save
  - [ ] Editing one chunk marks only that chunk stale
- **Tests:** e2e_US017_studio_edit_validate_save, e2e_US017_studio_marker_autocomplete
- **Depends on:** S5-T02

### S5-T04: Take comparison
- **Labels:** type: feature, area: studio, priority: p1, size: M, sprint: 5
- **Estimate:** M
- **Spec refs:** PRD FR-022, FR-013
- **Description:** Render another take with new seed, play takes A and B, show similarity score and duration, keep best.
- **Acceptance criteria:**
  - [ ] `e2e_US017_studio_compare_takes_keep_best` passes
- **Tests:** e2e_US017_studio_compare_takes_keep_best
- **Depends on:** S5-T03

### S5-T05: Full preview and approve
- **Labels:** type: feature, area: studio, priority: p1, size: S, sprint: 5
- **Estimate:** S
- **Spec refs:** PRD FR-022, FR-018
- **Description:** Re-master and play the full track in the real `<audio-smith-player>`, approve button, optional inject from UI with diff preview.
- **Acceptance criteria:**
  - [ ] Approve persists
  - [ ] Inject diff shown before write
- **Tests:** e2e_US017_studio_approve_persists, e2e_US017_studio_inject_diff_shown_before_write
- **Depends on:** S5-T04, S4-T03

### Sprint 5 Gate
Hard stop. Sprint 6 does not start until every item is checked.
- [ ] Author can edit one chunk, re-render only it, compare takes, approve, and inject without leaving Studio
- [ ] Studio makes zero external requests
- [ ] Retrospective written, `sprint-5-complete` tagged

---

## Sprint 6: Release v1.0.0

**Milestone:** Sprint 6: Release v1.0.0
**Duration:** 1 week
**Goal:** Ship v1.0.0 to PyPI and npm with complete docs, hardened defaults, and passing listening tests.

### S6-T01: Security review and hardening
- **Labels:** type: security, area: ci, priority: p0, size: M, sprint: 6
- **Estimate:** M
- **Spec refs:** PRD NFR-005, NFR-006, ARCHITECTURE security guidelines
- **Description:** Walk the Security Guidelines checklist; add `pip-audit`, `bandit` (via ruff S rules), `npm audit`, `gitleaks` to CI; fuzz the extractor with hypothesis-generated HTML; verify SSRF guard against DNS rebinding (resolve once, connect to resolved IP).
- **Acceptance criteria:**
  - [ ] Zero high or critical findings
  - [ ] Report in `docs/SECURITY_REVIEW.md`
- **Tests:** test_fetch_dns_rebinding_connects_to_resolved_ip, test_extract_blocks_fuzz_html_never_crashes
- **Depends on:** S5-T05

### S6-T02: Documentation site content
- **Labels:** type: docs, area: cli, priority: p0, size: L, sprint: 6
- **Estimate:** L
- **Spec refs:** PRD NFR-012
- **Description:** README (template below), `docs/guide/` (quickstart, voices and consent, profiles, backends, site mode, GitHub Action, Studio, troubleshooting), `docs/reference/` (CLI generated via typer docs, Python API via mkdocstrings), mkdocs-material site deployed to GitHub Pages at getaudiosmith.com (DNS for the custom domain is a manual owner step).
- **Acceptance criteria:**
  - [ ] Every CLI command and flag documented
  - [ ] Quickstart runs in under 10 minutes on a fresh machine
  - [ ] Docs build with `mkdocs build --strict`
- **Tests:** test_docs_every_cli_flag_documented, smoke_docs_mkdocs_build_strict
- **Depends on:** S6-T01

### S6-T03: THIRD_PARTY_LICENSES.md
- **Labels:** type: docs, area: packaging, priority: p0, size: S, sprint: 6
- **Estimate:** S
- **Spec refs:** PRD NFR-008
- **Description:** Generate with `pip-licenses` and `license-checker` for npm; add model weights section (Maya 2 Native: Apache-2.0; Kokoro-82M: Apache-2.0; Chatterbox: MIT; resemblyzer: Apache-2.0) and assets. Verify every entry at implementation time.
- **Acceptance criteria:**
  - [ ] CI job fails if a new dependency lacks an entry
- **Tests:** test_licenses_new_dependency_without_entry_fails
- **Depends on:** S6-T01

### S6-T04: Listening test round
- **Labels:** type: test, area: qa, priority: p0, size: S, sprint: 6
- **Estimate:** S
- **Spec refs:** PRD NFR-004, TEST_PLAN listening protocol
- **Description:** Run the TEST_PLAN listening protocol on 3 letters (en) and 1 letter (hi). Record scores in `docs/LISTENING_TESTS.md`. This is a human step and cannot be performed by the executing agent; the agent prepares the audio and the scoring sheet and marks the task deferred until the owner records scores.
- **Acceptance criteria:**
  - [ ] All averages 4 or higher
  - [ ] Scores recorded by a human listener in `docs/LISTENING_TESTS.md`
- **Tests:** none
- **Depends on:** S6-T02

### S6-T05: Release pipeline
- **Labels:** type: chore, area: packaging, priority: p0, size: M, sprint: 6
- **Estimate:** M
- **Spec refs:** PRD NFR-010, ARCHITECTURE Versioning section
- **Description:** `.github/workflows/release.yml` per the Versioning section: on tag `v*.*.*`, verify versions, build sdist and wheel with `uv build`, publish to PyPI via trusted publishing (OIDC, no tokens), build and publish npm packages with provenance, create GitHub Release with changelog body, attach SBOM (CycloneDX) and artifacts. Configuring the trusted publishers on PyPI and npm is a manual owner step.
- **Acceptance criteria:**
  - [ ] Dry run to TestPyPI succeeds from a `v1.0.0-rc.1` tag (requires owner trusted-publisher setup; deferred otherwise)
  - [ ] Workflow uses no long-lived publishing tokens
- **Tests:** none
- **Depends on:** S6-T03

### S6-T06: Ship v1.0.0
- **Labels:** type: chore, area: packaging, priority: p0, size: S, sprint: 6
- **Estimate:** S
- **Spec refs:** PRD NFR-010, ARCHITECTURE Versioning section
- **Description:** Follow the release checklist exactly; then narrate every letter on the reference site with the published version as the launch validation.
- **Acceptance criteria:**
  - [ ] `uv tool install mr-audio-smith` installs v1.0.0
  - [ ] Reference site letters have players
- **Tests:** smoke_release_installed_version_is_1_0_0
- **Depends on:** S6-T04, S6-T05

### Sprint 6 Gate
Hard stop. Sprint 7 does not start until every item is checked.
- [ ] Release checklist complete
- [ ] v1.0.0 on PyPI and npm with provenance
- [ ] Docs site live
- [ ] Reference site narrated with v1.0.0
- [ ] Retrospective written, `sprint-6-complete` tagged, `v1.0.0` annotated tag on `main`

---

## Sprint 7: Server and MCP

**Milestone:** Sprint 7: Server and MCP
**Duration:** 1 week
**Goal:** mr-audio-smith runs as a service other machines and agents can call.

### S7-T01: REST server with job queue
- **Labels:** type: feature, area: server, priority: p0, size: L, sprint: 7
- **Estimate:** L
- **Spec refs:** PRD FR-023, ARCHITECTURE REST contract
- **Description:** FastAPI app per ARCHITECTURE REST contract. Single GPU worker consuming an asyncio queue; jobs persisted to SQLite (`jobs.db`) so restarts keep history; artifacts under `OUT_DIR/jobs/{id}`. Progress reported per stage and chunk.
- **Acceptance criteria:**
  - [ ] FR-023 ACs met
  - [ ] Jobs survive restart
  - [ ] Concurrent submissions queue in order
- **Tests:** test_server_job_survives_restart, test_server_concurrent_jobs_run_in_submission_order, test_server_progress_reported_per_stage
- **Depends on:** S6-T06

### S7-T02: Auth, limits, health
- **Labels:** type: security, area: server, priority: p0, size: M, sprint: 7
- **Estimate:** M
- **Spec refs:** PRD FR-023, NFR-005
- **Description:** Bearer token required on non-localhost bind; rate limiting; `/healthz`, `/readyz` (Maya 2 reachable, model loaded, ffmpeg present); problem+json errors.
- **Acceptance criteria:**
  - [ ] Auth tests pass
  - [ ] Readiness flips when backend is down
- **Tests:** test_server_non_localhost_bind_requires_token, test_server_missing_bearer_returns_401_problem_json, test_server_readyz_flips_when_backend_down, test_server_rate_limit_returns_429
- **Depends on:** S7-T01

### S7-T03: MCP server
- **Labels:** type: feature, area: mcp, priority: p0, size: L, sprint: 7
- **Estimate:** L
- **Spec refs:** PRD FR-024, NFR-005
- **Description:** Official Python MCP SDK; transports stdio and streamable HTTP. Tools are `mr_audio_smith_narrate {source, profile?, voice?, backend?, langs?, inject_path?}` returning `{manifest_path, tracks:[{lang, file, duration_s}], warnings}` (long-running, emits progress notifications per stage); `mr_audio_smith_script {source, profile?}` returning `{script_path, chunks, est_minutes}`; `mr_audio_smith_render {script_path, chunks?, voice?, backend?}` returning `{files}`; `mr_audio_smith_list_voices {}` returning `[{id, display_name, backends, cloned}]`; `mr_audio_smith_list_profiles {}` returning `[{id, version, description}]`; `mr_audio_smith_list_backends {}` returning `[{id, available, languages, cloning, license}]`; `mr_audio_smith_status {}` returning the doctor report as JSON; `mr_audio_smith_recommend {source | description}` returning `{profile, backend, reason}`. Tool descriptions state that cloning requires a registered voice with consent, so agents do not try to bypass it. File paths returned are absolute.
- **Acceptance criteria:**
  - [ ] FR-024 ACs met
  - [ ] MCP inspector lists all tools with valid schemas
  - [ ] Integration test drives `narrate` with mocks over stdio
  - [ ] Every returned file path is absolute
- **Tests:** it_mcp_stdio_narrate_mock_returns_manifest, test_mcp_tools_list_all_eight_with_valid_schemas, test_mcp_narrate_unregistered_voice_clone_refused, test_mcp_returned_paths_absolute
- **Depends on:** S7-T01

### S7-T04: Remote mode for CLI and Action
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 7
- **Estimate:** M
- **Spec refs:** PRD FR-023, FR-025
- **Description:** `--server URL --token ...` makes `run` and `site` submit jobs remotely and download artifacts; the GitHub Action uses this path when `server-url` is set.
- **Acceptance criteria:**
  - [ ] End-to-end test against a local server process
  - [ ] Token is never written to logs or the manifest
- **Tests:** it_remote_mode_run_against_local_server, test_remote_token_not_logged
- **Depends on:** S7-T02

### Sprint 7 Gate
Hard stop. Sprint 8 does not start until every item is checked.
- [ ] Server runs on the GPU box; a laptop narrates a page through it (manual step on owner hardware)
- [ ] MCP tools work from Claude Code via stdio
- [ ] Coverage for `server` and `mcp_server` at or above targets
- [ ] Retrospective written, `sprint-7-complete` tagged

---

## Sprint 8: Harness Integrations

**Milestone:** Sprint 8: Harness Integrations
**Duration:** 1 week
**Goal:** "Narrate this page for my kid" works from Pi, Goose, OpenCode, and Claude Code.

| Harness | Integration | Why |
|---|---|---|
| Pi | `@mr-audio-smith/pi-extension` built on `pi-agent-core` + TypeBox tools, calling the REST server | Slash commands, streaming progress via `onUpdate`, context hook that lists available voices and profiles |
| Goose | `integrations/goose/toolkit.yaml` pointing at the MCP server (stdio) | Goose speaks MCP natively |
| OpenCode | `integrations/opencode/opencode.json.example` + README | OpenCode speaks MCP natively, zero code |
| Claude Code | MCP config snippet + `integrations/claude-code/skill/SKILL.md` + repo `CLAUDE.md`/`AGENTS.md` | Native MCP and file-based context |

### S8-T01: Pi extension
- **Labels:** type: feature, area: harness, priority: p0, size: L, sprint: 8
- **Estimate:** L
- **Spec refs:** PRD FR-024, FR-023
- **Description:** TypeBox schemas mirroring MCP tools; slash commands `/narrate <url> [profile] [voice]`, `/voices`, `/audio-status`; streams job progress through `onUpdate`; context extension injects available voices and profiles at session start; config via `AUDIO_SMITH_SERVER_URL` and token.
- **Acceptance criteria:**
  - [ ] vitest unit tests with mocked server
  - [ ] Manual test in Pi recorded in TEST_PLAN
- **Tests:** test_pi_narrate_command_streams_progress, test_pi_context_hook_lists_voices_and_profiles, test_pi_schemas_match_mcp_tools
- **Depends on:** S7-T04

### S8-T02: Goose toolkit
- **Labels:** type: feature, area: harness, priority: p1, size: S, sprint: 8
- **Estimate:** S
- **Spec refs:** PRD FR-024
- **Description:** `toolkit.yaml` launching `mr-audio-smith mcp --transport stdio`; README section.
- **Acceptance criteria:**
  - [ ] Smoke test listing tools from Goose
- **Tests:** smoke_goose_toolkit_lists_tools
- **Depends on:** S7-T04

### S8-T03: OpenCode config
- **Labels:** type: docs, area: harness, priority: p1, size: S, sprint: 8
- **Estimate:** S
- **Spec refs:** PRD FR-024
- **Description:** Config snippet and README section.
- **Acceptance criteria:**
  - [ ] Smoke test listing tools from OpenCode
- **Tests:** smoke_opencode_config_lists_tools
- **Depends on:** S7-T04

### S8-T04: Claude Code skill
- **Labels:** type: feature, area: harness, priority: p1, size: M, sprint: 8
- **Estimate:** M
- **Spec refs:** PRD FR-024, NFR-005
- **Description:** A skill (`SKILL.md`) teaching Claude Code when and how to call the MCP tools, the consent rule, how to review a script before rendering, and how to inject into a static site; `claude mcp add` instructions.
- **Acceptance criteria:**
  - [ ] Skill loads
  - [ ] A scripted session narrates the fixture page
- **Tests:** smoke_claude_code_skill_scripted_session_narrates_fixture
- **Depends on:** S7-T04

### S8-T05: Harness smoke tests in CI
- **Labels:** type: test, area: ci, priority: p2, size: M, sprint: 8
- **Estimate:** M
- **Spec refs:** PRD FR-024, NFR-009
- **Description:** `harness-smoke-tests` job on staging and release: MCP stdio handshake and `tools/list`; Pi extension unit tests.
- **Acceptance criteria:**
  - [ ] Job green on staging
- **Tests:** smoke_mcp_stdio_handshake_tools_list
- **Depends on:** S8-T01, S8-T02, S8-T03, S8-T04

### Sprint 8 Gate
Hard stop. Sprint 9 does not start until every item is checked.
- [ ] Each harness narrates the fixture page with mocks in a recorded session
- [ ] Docs list setup steps for all four harnesses
- [ ] Retrospective written, `sprint-8-complete` tagged

---

## Sprint 9: Packaging and Deployment

**Milestone:** Sprint 9: Packaging
**Duration:** 1 week
**Goal:** Three deployment tiers, all documented and tested.

### Deployment tiers (reference for S9-T01 to S9-T04)

Tier 1, local binary: `uv tool install mr-audio-smith[...]` (primary); `pipx` documented as an alternative. Maya 2 server run locally per its README; `mr-audio-smith doctor` verifies it.

Tier 2, Docker Compose. `deploy/docker-compose.local.yml` (note: the Maya 2 server port is 8080 per the verified upstream default; the source prompt's 8000 is corrected here):

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    volumes: [ollama:/root/.ollama]
    healthcheck: {test: ["CMD", "ollama", "list"], interval: 10s, retries: 30}
    deploy: {resources: {reservations: {devices: [{capabilities: [gpu]}]}}}
  ollama-pull:
    image: ollama/ollama:latest
    depends_on: {ollama: {condition: service_healthy}}
    environment: {OLLAMA_HOST: http://ollama:11434}
    entrypoint: ["ollama", "pull", "qwen3:14b"]
    restart: "no"
  maya2:
    image: ghcr.io/serverless-ventures/maya2-server:pinned   # built from upstream; pin digest
    volumes: [models:/models]
    healthcheck: {test: ["CMD", "curl", "-fsS", "http://localhost:8080/health"], interval: 15s, retries: 40}
    deploy: {resources: {reservations: {devices: [{capabilities: [gpu]}]}}}
  audio-smith:
    image: ghcr.io/serverless-ventures/mr-audio-smith:${VERSION:-latest}
    command: ["serve", "--host", "0.0.0.0"]
    environment:
      AUDIO_SMITH_MAYA2_URL: http://maya2:8080/v1
      OLLAMA_HOST: http://ollama:11434
      AUDIO_SMITH_SERVER_TOKEN: ${AUDIO_SMITH_SERVER_TOKEN:?set a token}
    ports: ["127.0.0.1:7340:7340"]
    volumes: [cache:/var/lib/audio-smith/cache, out:/var/lib/audio-smith/out, voices:/var/lib/audio-smith/voices]
    depends_on:
      maya2: {condition: service_healthy}
      ollama-pull: {condition: service_completed_successfully}
volumes: {ollama: {}, models: {}, cache: {}, out: {}, voices: {}}
```

`deploy/docker-compose.prod.yml`: images pinned by digest, CPU and memory limits, read-only root filesystems, internal network for ollama and maya2 (no published ports), only audio-smith published behind a reverse proxy with TLS, restart policies, log rotation.

Tier 3, Kubernetes via Helm (`charts/mr-audio-smith`):

- StatefulSet `maya2`: GPU (`nvidia.com/gpu: 1`) via NVIDIA device plugin, PVC `models` (50Gi), init container pre-downloads and checksums weights, readiness probe on `/health`.
- StatefulSet `ollama` (optional, `ollama.enabled`): PVC 100Gi, init job pulls the script model. Alternatively point at an existing vLLM OpenAI-compatible endpoint (on NVIDIA Grace arm64 nodes, use `nvcr.io/nvidia/vllm-openai:latest`).
- Deployment `audio-smith`: API layer, HPA on CPU and queue depth (custom metric), PVC `cache` (ReadWriteMany if replicas > 1) and `voices` (secret-like, 0700), Secret for `AUDIO_SMITH_SERVER_TOKEN`.
- Ingress: TLS, `proxy-read-timeout: 600`, `proxy-body-size: 10m`, auth annotation.
- NetworkPolicy: only audio-smith may reach maya2 and ollama.
- Values for k3s with Cilium on a 2-node GPU cluster provided as `values-k3s-gpu.yaml`.

### S9-T01: Dockerfiles
- **Labels:** type: chore, area: packaging, priority: p0, size: L, sprint: 9
- **Estimate:** L
- **Spec refs:** PRD NFR-001, NFR-002, ARCHITECTURE ADR-017
- **Description:** `Dockerfile.cpu` (python slim, ffmpeg, Kokoro extra, non-root) and `Dockerfile.cuda` (NVIDIA CUDA 12.8 runtime base, torch CUDA wheels), both multi-arch amd64 and arm64; build cache in GHA. The CPU image uses Python 3.12 because of the Kokoro constraint (ADR-017).
- **Acceptance criteria:**
  - [ ] Images run `doctor` green
  - [ ] CPU image under 1.5 GB
  - [ ] Containers run as a non-root user
- **Tests:** smoke_docker_cpu_image_doctor_green, test_docker_cpu_image_size_under_1_5gb
- **Depends on:** S7-T04

### S9-T02: Compose files and model pre-puller
- **Labels:** type: chore, area: packaging, priority: p0, size: M, sprint: 9
- **Estimate:** M
- **Spec refs:** PRD NFR-001, NFR-005
- **Description:** Author `deploy/docker-compose.local.yml` and `deploy/docker-compose.prod.yml` as specified in the Tier 2 reference above, plus the model pre-puller (the `ollama-pull` service and a weights pre-download and checksum step for the Maya 2 model volume) so first start needs no manual model steps. The prod file pins images by digest, sets CPU and memory limits, read-only root filesystems, an internal network for ollama and maya2, publishes only audio-smith behind a TLS reverse proxy, and sets restart policies and log rotation.
- **Acceptance criteria:**
  - [ ] `docker compose -f deploy/docker-compose.local.yml up` narrates the fixture page via the API on a GPU host (manual on owner GPU hardware; `docker compose config` validation runs in CI)
  - [ ] Compose files validate with `docker compose config`
  - [ ] Prod file publishes no ports for ollama or maya2
- **Tests:** test_compose_local_config_validates, test_compose_prod_no_published_ports_for_internal_services
- **Depends on:** S9-T01

### S9-T03: Helm chart
- **Labels:** type: chore, area: packaging, priority: p0, size: L, sprint: 9
- **Estimate:** L
- **Spec refs:** PRD NFR-001, NFR-005
- **Description:** Create `charts/mr-audio-smith` implementing the Tier 3 reference above: maya2 and optional ollama StatefulSets, the audio-smith Deployment with HPA, PVCs, Secret, Ingress, NetworkPolicy, and `values-k3s-gpu.yaml`.
- **Acceptance criteria:**
  - [ ] `helm lint` and `helm template` pass
  - [ ] `ct install` in kind with the CPU profile (mock backend)
  - [ ] Manual install on the GPU cluster documented
- **Tests:** test_helm_lint_passes, test_helm_template_networkpolicy_restricts_maya2, smoke_helm_ct_install_kind_cpu_profile
- **Depends on:** S9-T01

### S9-T04: Signing and publishing
- **Labels:** type: chore, area: packaging, priority: p1, size: M, sprint: 9
- **Estimate:** M
- **Spec refs:** PRD NFR-006, NFR-010
- **Description:** cosign keyless signing for images and chart; SBOM attestation; release workflow publishes images and chart. Publishing to GHCR requires the owner to enable package permissions; until then the workflow is validated with a dry run.
- **Acceptance criteria:**
  - [ ] `cosign verify` succeeds for released images
  - [ ] SBOM attestation attached to each image
- **Tests:** smoke_cosign_verify_released_image
- **Depends on:** S9-T02, S9-T03

### Sprint 9 Gate
Hard stop. Release v1.1.0 only after every item is checked.
- [ ] All three tiers documented and tested
- [ ] Signed images and chart published for the current version
- [ ] Retrospective written, `sprint-9-complete` tagged; release v1.1.0

---

## Out of scope (enhancement issues)

Each item below becomes a GitHub issue with the `enhancement` label. These are deliberately not built in v1.

### OOS-01: Desktop app (Tauri)
- **Labels:** enhancement
- **Description:** Studio on localhost covers review for v1. Revisit a Tauri desktop wrapper if non-engineer authors adopt Studio and the localhost workflow proves a barrier.

### OOS-02: Hosted SaaS (accounts, billing)
- **Labels:** enhancement
- **Description:** Local-first comes first. A hosted tier conflicts with the zero-telemetry principle until accounts, billing, voice-clip custody, and consent handling are designed carefully.

### OOS-03: Inline emotion tags
- **Labels:** enhancement
- **Description:** Maya 2 does not support inline tags. Add them when a backend that supports tags is integrated (for example a Maya1 adapter); the script marker set and validator would then need a backend-gated extension.

### OOS-04: Forced alignment for word-level captions and read-along highlighting
- **Labels:** enhancement
- **Description:** High value for kids, and it refines the sentence-level WebVTT from S3-T07, but it needs an aligner model. A v1.1 candidate.

### OOS-05: Multi-voice dialogue (narrator plus characters)
- **Labels:** enhancement
- **Description:** Needs script schema changes (speaker attribution per chunk) and multi-voice consent handling.

### OOS-06: Podcast RSS feed generation
- **Labels:** enhancement
- **Description:** An easy follow-on once manifests exist: generate an RSS feed from a set of manifests and their MP3 files.

### OOS-07: Fine-tuning a personal voice
- **Labels:** enhancement
- **Description:** Zero-shot cloning is good enough for v1. Fine-tuning would add training infrastructure and a larger consent and storage surface.

### OOS-08: PDF, EPUB, and Google Docs sources
- **Labels:** enhancement
- **Description:** HTML and Markdown first. Additional sources would each need an extractor that emits the same Block model.

### OOS-09: Redis-backed distributed job queue
- **Labels:** enhancement
- **Description:** A single GPU worker with the SQLite-backed queue is enough for v1. Revisit when multiple GPU workers are needed.

### OOS-10: Background music library
- **Labels:** enhancement
- **Description:** v1 ships two original stings only; users bring their own music bed. A curated library raises licensing questions.

### OOS-11: Mobile apps and offline kid app (PWA)
- **Labels:** enhancement
- **Description:** A separate product built on top of the published audio and manifests.

### OOS-12: Live streaming synthesis to the player
- **Labels:** enhancement
- **Description:** Needs server push and a streaming player path; batch rendering is sufficient for static sites.
