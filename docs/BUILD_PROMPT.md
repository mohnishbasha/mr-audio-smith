# MR-AUDIO-SMITH: Master Build Prompt
## Local-first page-to-narration engine: turn any web page into a realistic, audience-tuned audio narrative with an embeddable player

---

## Project Identity

**Name:** `mr-audio-smith`
**Family:** The "smith" toolset from SnackOnAI (siblings: `mr-pixel-smith`, `mr-reel-smith`, `mr-motion-smith`)
**GitHub repo:** `mohnishbasha/mr-audio-smith` (standalone repo; mirrored as `snackonai/mr-audio-smith/` via git subtree for the SnackOnAI tutorial series)
**Primary domain:** `getaudiosmith.com` (preferred) with `mraudiosmith.com` as fallback
**Python package (PyPI):** `mr-audio-smith` (import name `audio_smith`, console script `mr-audio-smith`)
**npm scope:** `@mr-audio-smith` (for `@mr-audio-smith/player` and `@mr-audio-smith/pi-extension`)
**Container image:** `ghcr.io/serverless-ventures/mr-audio-smith` (server + MCP, CUDA and CPU variants)
**Tagline:** *Every page deserves a voice.*
**Short description (GitHub About field):** Turn any web page into a realistic, audience-tuned narration with your own cloned voice, generated locally, embedded with one tag.
**Repository visibility:** Public, MIT licensed
**Distribution model:** Open-source, MIT (consistent with mr-pixel-smith). Free forever for self-hosting.
**License:** MIT © 2026 Serverless Ventures LLC
**Long description (README opening):** mr-audio-smith reads a web page, rewrites it into a script tuned for a specific listener (a five-year-old, a commuter, a busy executive), and renders it as natural speech using local open models such as Maya 2 Native with zero-shot voice cloning. It outputs a mastered MP3, captions, and a drop-in player snippet, and only re-renders what changed.

**Why mr-audio-smith:** The smith family names describe a craftsperson who forges one medium. Pixel smith forges images, reel smith forges short videos, motion smith forges animation. Audio smith forges sound: it takes raw text, heats it in the script stage, shapes it with a voice, and polishes it in mastering. The "mr" prefix keeps the family friendly and memorable, which matters for a tool whose flagship use case is narrating letters to a child.

**Flagship use case (drives every design decision):** A parent publishes letters to their five-year-old on a personal site (reference site: `https://www.aadhish.us/messages-from-dad.html`, example letter: `https://www.aadhish.us/letter-calm-in-the-chaos.html`). Each letter must get an audio version read in the parent's own cloned voice, rewritten for a five-year-old listener, embedded on the letter page as a "Listen" option, regenerated automatically when a letter is added or edited.

---

## Amendments recorded during execution (2026-11-02)

The executing agent verified facts and made decisions that change or sharpen this prompt. The spec
documents in `docs/` are the source of truth (Spec Change Protocol); this section mirrors them so the
prompt stays accurate. Inline text below has been corrected where it was factually wrong.

**Verified upstream facts (Maya 2 Native, github.com/MayaResearch/maya2-native, `maya3/client.py` and `maya3/server.py`)**
- Server: `python -m maya3.server --ckpt maya-research/maya2-native --host 127.0.0.1 --port 8080 --max-seats N`. Default port is **8080**, not 8000, so `AUDIO_SMITH_MAYA2_URL` defaults to `http://127.0.0.1:8080/v1` and compose and Helm probes use 8080.
- Speech: `POST /v1/audio/speech` `{model: "maya3", input, voice, language, response_format: "wav", normalize, seed, temperature (0.1..1.5), top_k, top_p, repetition_penalty, speed}`; **`speed` must be 1.0**, so speaking rate is applied after synthesis with ffmpeg `atempo` (ADR-016). Same seed, text, and voice give the same audio. 24 kHz mono.
- Cloning: `POST /v1/voices` `{voice_id, ref_audio_b64, ref_text, lang, mode: icl_spk|icl|spk, replace}`; `GET /v1/voices`; `DELETE /v1/voices/{id}`. The adapter registers each consented clip as `as-{voice_id}-{clip_hash[:8]}`.
- Health: `GET /health` returns 503 while loading and 200 when ready. Errors are `{"error": {message, type, code, param}}`; 503 is retryable.
- In-process: `maya3.Maya3TTS.from_pretrained(...)`, `.generate(text, lang, voice)`, `.register_voice(...)`. `maya3` is **not on PyPI**, so the `maya2` extra only adds torch and the README documents the git install. Needs a Linux NVIDIA GPU (about 8 GB VRAM); no Apple MPS.

**New decisions (ADRs added to docs/ARCHITECTURE.md)**
- ADR-015: speaker similarity uses resemblyzer (`qa` extra), lazy-imported; skipped with a manifest warning when absent.
- ADR-016: Maya 2 speaking rate is applied post-synthesis with ffmpeg `atempo`.
- ADR-017: Kokoro does not install on Python 3.13+; the `kokoro` and `chatterbox` extras carry `python_version < "3.13"` markers and doctor hints to use 3.12.
- ADR-018: delivery is one feature branch and one PR per sprint (`feature/sprint-N-<slug>`) that closes all of that sprint's issues, instead of one PR per task, because a single autonomous agent executes the plan. TDD, the Spec Change Protocol, and per-issue implementation comments still apply.

**Contract and default changes**
- Default profile is `kid-5` (the flagship listener), configurable with `AUDIO_SMITH_DEFAULT_PROFILE`.
- LLM provider strings keep this prompt's format: `ollama:<model>`, `anthropic:<model-id>`, `openai_compat:<base_url>#<model>`, plus `fake` or `fake:<fixture-dir>` for tests.
- Blocks cache key is `H(page bytes, extractor version, parent_headings)` (the content hash cannot be known before extraction); scripts, chunks, and tracks keep the keys in the Caching model, and the script key also includes the writer prompt template version and the track.
- Local `.md` sources are converted to HTML and use the same extractor.
- Script writer: the target-length check (plus or minus 20 percent) triggers the single corrective retry; if the retry is still off-length the result is kept with a warning (only grammar violations fail the run).
- Profiles: `writing.parent_headings` routes a container whose first child is a matching label (or an `h2`-`h6` section with a matching heading) to the parent track; it is opt-in and the core has no magic strings.
- Typed errors gain `LLMError` (code `llm_failed`, stage `script`, exit 5).
- New helper modules: `audio_smith/proc.py` (the only place subprocesses start: argument arrays, timeouts), `audio_smith/paths.py` (`safe_slug`, `ensure_inside`, `atomic_write`), `audio_smith/preflight.py` (`PreflightIssue`), `audio_smith/cli_commands.py` (stage commands; also a front door under the import-linter contract).
- Dependencies: `selectolax>=1.0` with the lexbor backend; `typer` vendors click (do not import click); `audioop-lts` on Python 3.13 for pydub.

- Sprint 2: in-process Maya 2 is selected with `AUDIO_SMITH_MAYA2_MODE=inproc`; Chatterbox, like Maya 2, applies rate after synthesis; `require_consent()` re-reads the voice record and re-hashes the clip inside every cloning backend; the installed `openai` SDK uses `httpx2`, so SDK calls are tested with an injected client and mock transport while plain httpx calls use respx; a minimal `render` command lands in Sprint 2 (per-chunk WAVs) and Sprint 3 extends it with the chunk planner, cache, QA, and mastering.

- Sprint 3: verbatim passages and the signature are enforced by code (`script/verbatim.py`) rather than trusted to the LLM (the live gate showed qwen3:14b blanking the signature chunk); finished tracks are cached under `tracks/` so unchanged re-runs skip ffmpeg; `render` without `--chunks` produces the mastered track and with `--chunks` writes WAV previews; the manifest track gains `captions` and optional `opus`; the `qa` extra pins `setuptools<81` because resemblyzer imports `pkg_resources`; unit tests that master audio need ffmpeg, so CI installs it on every OS.

- Sprints 4 and 5 (built in parallel, delivered in one PR): every run writes `<slug>.embed.html` and copies the player bundle; `embed_*` settings configure label, size, and paths; `run` gains `--lang`, `--inject`, `--selector`; Studio media is fetched with the session token and handed to elements as `blob:` URLs, so the Studio CSP is `connect-src 'self' blob:` (one addition to the prompt's CSP); Studio core lives in `audio_smith/review*.py` and is re-exported as `api.review_*`; take numbers start at 1 and take 0 is the original narration.

**Tooling added**
- `scripts/sync-test-plan.py` marks TEST_PLAN rows Automated when a test with that exact id exists and appends unplanned tests to section 5.28; CI runs it with `--check`.
- `scripts/record-llm.py` (`make record-llm`) records real Ollama responses into `tests/fixtures/llm/` for the fake provider; the golden script is the replay of that recording.
- `scripts/check_em_dash.py` is the em dash hook; `scripts/create-issues.py` retries `gh` with backoff (GitHub rate-limits issue bursts).
- pytest collects `test_*`, `it_*`, `smoke_*`, `e2e_*`, `regression_*` functions so TEST_PLAN ids are real test names.
- `gpu-integration` lives in its own workflow and runs only when the repository variable `GPU_RUNNER_ENABLED` is `true`, so PRs never wait for a runner that does not exist.

**GitHub setup as executed**
- The repo was created from the local first commit (not with `--license/--gitignore`, which would have created a conflicting initial commit). Issues #1 to #68 are the sprint tasks in plan order (S0-T01 is #1, S9-T04 is #68); #69 to #80 are the out-of-scope enhancements.
- The label taxonomy is 50 labels (the "44" count above undercounts the list); GitHub's default labels were removed.
- The project board needs the `project` token scope (`gh auth refresh -s project,read:project`); `scripts/create-issues.py --project-only --project N` adds existing issues afterwards.
- Promotion `develop` to `staging` (and `staging` to `main`) is a fast-forward of the target to the CI-verified commit, done by the admin after the promotion PR is green; GitHub then marks the PR merged. Squash-merging `develop` into `staging` made the branches diverge and conflict on the next promotion, so it is not used. (Sprint 0 was squash-promoted; staging was realigned to `develop` once on 2026-11-02.)
- Branch protection: required approvals cannot be satisfied by a single-maintainer agent, so `enforce_admins` is false and release PRs into `staging`/`main` are merged by the admin; status checks are still required.

**Cannot be completed by the agent (tracked as manual steps)**
- GPU-runner Maya 2 integration, human listening tests, publishing to PyPI, npm, and GHCR (owner must configure trusted publishing), DNS for getaudiosmith.com.

---

## EXECUTION ORDER: THIS IS MANDATORY

The first action you take when executing this prompt is to generate the five product specification documents listed in Step 1 below. No GitHub setup, no scaffolding, no code of any kind is written before those documents exist on disk and are committed.

1. **Step 1:** Generate `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/SPRINT_PLAN.md`, `docs/TEST_PLAN.md`. Commit them on `main` as the first commit: `docs: add product specification documents`.
2. **Step 2:** Create and configure the GitHub repository (branches, protection, labels, milestones, project board, templates).
3. **Step 3:** Create every GitHub issue for every sprint task defined in `docs/SPRINT_PLAN.md`.
4. **Step 4 onward:** Execute sprints in order, Sprint 0 through Sprint 9, following the Sprint Start Protocol, Spec Change Protocol, Test Scenario Generation Protocol, and Sprint End Protocol. Every sprint gate is a hard stop.

If you are about to write code and Step 1 is not complete, stop. Complete Step 1 first.

**Spec documents supersede this prompt.** Once `docs/PRD.md` exists it is the source of truth for product behavior. Once `docs/ARCHITECTURE.md` exists it is the source of truth for structure and contracts. If this prompt and a spec doc disagree after Step 1, the spec doc wins, and any change to a spec doc follows the Spec Change Protocol.

---

## Step 1: Product Specification Documents

Generate all five documents in full. Each document must be complete enough that an engineer who has never read this prompt can build from it. Use the content below as the minimum; expand where detail is missing, never shrink.

### 1.1 `docs/PRD.md`

#### Required sections

1. Overview (problem, solution, flagship use case)
2. Personas
3. User stories (US-001 onward)
4. Functional requirements (FR-001 onward) with acceptance criteria for every FR
5. Non-functional requirements (NFR-001 onward)
6. Success metrics
7. Constraints and assumptions
8. Out of scope for v1 (mirrors the "Out of Scope" section of this prompt)
9. Glossary

#### Problem statement

Written content on personal sites, newsletters, and blogs is only reachable by readers. Young children cannot read it yet, commuters cannot read while driving, and many people simply prefer listening. Existing text-to-speech readers read the page verbatim: they pronounce headings, list numbers, emoji names, and navigation, in a generic voice, at one pace, for one imagined adult listener. Cloud narration services sound better but cost money per character, send private family content to third parties, and do not adapt the text to the listener.

#### Solution statement

mr-audio-smith is a local-first pipeline with five stages: extract the real content of a page, rewrite it into a listening script for a named audience profile, synthesize it paragraph by paragraph with a pluggable TTS backend (default: Maya 2 Native with the author's cloned voice), master it into a consistent, pleasant listening experience, and publish an MP3 plus captions plus a drop-in player. Every artifact is cached by content hash so rebuilding a whole site only renders what changed.

#### Personas

| ID | Persona | Goal | Technical level |
|---|---|---|---|
| P-1 | **Parent author** (flagship) | Letters to their child, narrated in their own voice, on their own site | Engineer comfortable with CLI and GitHub Actions |
| P-2 | **Newsletter writer** | Audio edition of each issue for subscribers who listen | Comfortable with CLI, may use the hosted player only |
| P-3 | **Agent operator** | Ask Claude Code, Pi, Goose or OpenCode to "narrate this page" and get files back | Uses agent harnesses daily |
| P-4 | **Platform team** | Run narration as a shared service for many sites | Kubernetes, GPUs |
| P-5 | **Listener** (child or adult) | Press play, hear a warm, clear, well-paced narration | Non-technical; for P-1 a five-year-old |

#### User stories (minimum set)

```
US-001  As a parent author, I run one command with a page URL and get an MP3 of that page
        narrated for a five-year-old, so my child can listen to my letter.
US-002  As a parent author, I register a short recording of my own voice once, so every
        narration sounds like me.
US-003  As a parent author, I review and edit the generated script before audio is rendered,
        so nothing is said that I did not intend.
US-004  As a parent author, I re-render a single paragraph after editing it, without
        re-rendering the whole letter.
US-005  As a parent author, I mark sections of my page (for example "A grown-up note") to be
        skipped or rendered as a separate parent track.
US-006  As a parent author, I add a player to my letter page with one snippet, so my child can
        press "Listen to Dad".
US-007  As a parent author, I get an additional language version (for example Hindi) in my own
        voice, so my child hears the letter in a heritage language.
US-008  As a parent author, a GitHub Action narrates every new or changed letter automatically
        when I push, so I never run anything by hand.
US-009  As a newsletter writer, I define my own audience profile (for example "commuter, 8
        minutes max") in YAML without changing code.
US-010  As a newsletter writer, I switch the TTS backend (local Maya 2, Kokoro on CPU, OpenAI
        cloud) with one flag.
US-011  As a listener, the narration has natural pauses, consistent volume, a short intro
        chime, and never reads emoji names, list numbers, or navigation text.
US-012  As a listener with hearing differences, I can turn on captions in the player.
US-013  As an agent operator, I call mr_audio_smith_narrate from my harness and receive file
        paths and a duration.
US-014  As a platform team, I deploy mr-audio-smith as an HTTP service on Kubernetes with GPU
        scheduling and a persistent cache.
US-015  As a parent author, the tool refuses to clone any voice that has not been registered
        with a consent record, so it cannot be misused to imitate someone.
US-016  As a parent author, I narrate every letter linked from an index page in one batch
        command.
US-017  As a parent author, I compare two takes of a paragraph side by side in a local review
        UI and keep the better one.
US-018  As any user, I run `mr-audio-smith doctor` and get a clear report of what is missing
        (ffmpeg, GPU, model weights, voice clip quality) before anything fails mid-run.
```

#### Functional requirements (minimum set, each with acceptance criteria)

```
FR-001  Fetch page
        Fetch an http(s) URL or read a local .html/.md file.
        AC: honors a configurable timeout (default 20s) and max size (default 5 MB);
            rejects non-http(s) schemes; sends a descriptive User-Agent;
            local files are read without network access.

FR-002  Extract narratable content
        Extraction order: (1) element with [data-narrate] attribute, (2) <article>,
        (3) trafilatura main-content extraction, (4) readability fallback.
        AC: navigation, header, footer, scripts, styles, forms are excluded;
            emoji are stripped; elements with data-narrate="skip" are excluded;
            elements with data-narrate="parent" go to the parent track;
            output is an ordered list of typed blocks:
            title, heading, paragraph, list_item, quote, signature.

FR-003  Content hashing
        Compute a SHA-256 over normalized extracted blocks plus profile id plus
        profile version plus backend id plus voice id plus language.
        AC: whitespace-only or markup-only changes to the page do not change the hash;
            any text change does.

FR-004  Audience profiles
        Load profiles from YAML (built-in: kid-5, kid-8, adult-commute, adult-brief).
        AC: schema-validated with clear errors; user profiles in ./profiles override
            built-ins of the same id; profile has a semantic version.

FR-005  Script generation
        Rewrite blocks into a listening script with an LLM provider
        (ollama default, anthropic, openai-compatible).
        AC: output is Script Markdown (see ARCHITECTURE) with numbered chunks;
            respects profile target_minutes within plus or minus 20 percent;
            preserves blocks marked data-narrate-verbatim exactly;
            preserves the signature block exactly;
            includes only pause markers and allowed emphasis markers;
            deterministic for temperature 0 with a fixed seed where provider supports it.

FR-006  Script validation
        Validate generated scripts before synthesis.
        AC: rejects unknown markers, empty chunks, chunks over max_chunk_chars;
            strips stray markdown and emoji; reports violations with chunk numbers;
            on failure retries the LLM once with the violations appended, then fails.

FR-007  Pronunciation lexicon
        Profile and project-level lexicons map words to phonetic respellings.
        AC: replacements are applied only at synthesis time, never to the stored script;
            whole-word, case-sensitive matching.

FR-008  Translation
        For each extra language in the profile, translate the validated script.
        AC: chunk boundaries and pause markers are preserved one to one;
            translated script stored as {slug}.{lang}.script.md.

FR-009  TTS backend interface
        Pluggable backends behind one interface: preflight(), list_voices(),
        synth(chunk, voice, params) -> PCM audio, capabilities().
        AC: backends: maya2 (default), kokoro (CPU fallback), openai (cloud),
            openai_compat (any OpenAI-compatible /v1/audio/speech server), mock (tests).

FR-010  Maya 2 Native backend
        Synthesize via the local Maya 2 Native server's OpenAI-compatible speech endpoint,
        with optional in-process mode via the Python package.
        AC: supports built-in voices and zero-shot cloning from a registered reference clip;
            supports all Maya 2 languages; returns 24 kHz mono PCM.

FR-011  Voice registry and consent
        Voices are registered with `mr-audio-smith voice add`.
        AC: registration requires a reference clip and a consent record
            (name, relationship "self" or "has written permission", date, statement);
            backends refuse clone requests for unregistered voices;
            clip quality is checked (duration 3 to 30 s, mono or downmixable,
            sample rate at least 16 kHz, clipping under 0.1 percent, SNR estimate at least 25 dB).

FR-012  Chunked synthesis
        Synthesize one script chunk at a time.
        AC: chunk results cached by chunk hash; failed chunks retried up to 2 times with
            backoff; partial progress survives interruption and resumes.

FR-013  Voice consistency QA
        Compute speaker embeddings per chunk and compare to the reference clip
        (or to chunk 1 for built-in voices).
        AC: chunks below the similarity threshold (default 0.75) are re-rendered with a new
            seed up to takes_per_chunk times; the best take is kept; report lists scores.

FR-014  Mastering
        Join chunks, insert silences for pause markers, add optional intro and outro stings,
        optional music bed with sidechain ducking, normalize loudness, encode.
        AC: integrated loudness -16 LUFS plus or minus 1, true peak at or below -1.5 dBTP;
            MP3 128 kbps mono 44.1 kHz by default; optional Opus;
            ID3 tags: title, artist (author), album (site name), date, cover art.

FR-015  Captions
        Produce WebVTT from chunk timings.
        AC: one cue per sentence, cue boundaries within 150 ms of audio,
            text from the narrated script (not the original page).

FR-016  Manifest
        Write {slug}.manifest.json with versions, hashes, backend, voice id, languages,
        durations, QA scores, and file names.
        AC: validates against the published JSON Schema.

FR-017  Embed snippet
        Produce {slug}.embed.html using the <audio-smith-player> web component, with a
        plain <audio> fallback inside it.
        AC: works with JavaScript disabled; includes captions track;
            language toggle when more than one language exists.

FR-018  Inject mode
        `--inject` writes the embed snippet into a local HTML file between
        <!-- audio-smith:start --> and <!-- audio-smith:end --> markers.
        AC: idempotent; creates markers after the configured selector if absent;
            never modifies anything outside the markers; dry-run prints a unified diff.

FR-019  Batch site mode
        `mr-audio-smith site <index-url> --match <glob>` narrates every matching linked page.
        AC: same-origin links only; respects a max-pages limit; skips unchanged pages by hash;
            prints a summary table.

FR-020  Cache
        Content-addressed cache directory for extracted blocks, scripts, chunk audio, and
        final outputs.
        AC: `cache prune --older-than 30d` works; cache key format is versioned.

FR-021  Doctor
        `mr-audio-smith doctor` checks Python version, ffmpeg, GPU and CUDA visibility,
        backend reachability, model weights presence, LLM provider reachability, registered
        voices, and disk space.
        AC: exit code 0 when all required checks pass; each failure has a fix hint.

FR-022  Studio review UI
        `mr-audio-smith studio` starts a localhost web UI to edit scripts, render and
        play individual chunks, compare takes, and approve a render.
        AC: binds to 127.0.0.1 only by default; no external network calls from the page.

FR-023  HTTP server
        `mr-audio-smith serve` exposes a REST API (see ARCHITECTURE) with async jobs.
        AC: job status endpoint; artifacts downloadable; optional bearer token auth.

FR-024  MCP server
        `mr-audio-smith mcp` exposes MCP tools over stdio and streamable HTTP.
        AC: tools listed in Appendix E are present and schema-valid.

FR-025  GitHub Action
        Composite action `mohnishbasha/mr-audio-smith/action@v1` narrates changed pages in
        a static-site repo and commits outputs.
        AC: runs only for files matching an input glob; supports a self-hosted GPU runner or
            a remote mr-audio-smith server URL; no-op when hashes are unchanged.

FR-026  Parent track
        Content marked data-narrate="parent" is rendered as a separate {slug}.parent.mp3
        using the adult-brief profile.
        AC: never included in the child track.
```

#### Non-functional requirements

```
NFR-001  Local-first: with default config, no page text, script, or audio leaves the machine.
NFR-002  Zero telemetry. No analytics, no crash reporting, no update pings.
NFR-003  Performance: a 4-minute-read letter renders end to end in under 3 minutes on a
         single modern NVIDIA GPU with Maya 2, and under 10 minutes on CPU with Kokoro.
NFR-004  Incremental: re-running on an unchanged page completes in under 2 seconds.
NFR-005  Reliability: any single chunk failure does not lose completed chunks.
NFR-006  Reproducibility: same inputs plus same seeds produce byte-identical scripts
         (LLM at temperature 0 where supported) and perceptually identical audio.
NFR-007  Accessibility: player meets WCAG 2.2 AA (keyboard operable, visible focus, 4.5:1
         contrast, captions, reduced-motion support, 44px minimum touch targets for children).
NFR-008  Portability: CLI runs on macOS (Apple Silicon), Linux x86_64, Linux arm64
         (including NVIDIA Grace-based systems), and Windows via WSL2.
NFR-009  Safety: voice cloning only from registered voices with consent records.
NFR-010  Observability: structured JSON logs with --log-format json; per-stage timings in the
         manifest.
NFR-011  Player weight: web component under 12 KB gzipped, no dependencies.
NFR-012  Licensing: every runtime dependency and every model weight has a recorded license
         in THIRD_PARTY_LICENSES.md; non-commercial weights are opt-in and flagged at runtime.
```

#### Success metrics

- Flagship: every letter on the reference site has an audio version within 10 minutes of being pushed.
- Listening quality: in a blind A/B, the parent prefers the mr-audio-smith script over a verbatim read in at least 9 of 10 letters.
- Voice similarity: mean speaker-similarity score at least 0.80 across chunks of a cloned voice.
- Incremental builds: at least 95 percent of site-mode runs render zero unchanged pages.

#### Glossary

| Term | Meaning |
|---|---|
| Block | One typed unit of extracted content (paragraph, heading, list item, quote, signature) |
| Script | The listening text produced by the script stage, in Script Markdown |
| Chunk | One numbered unit of the script that is synthesized in a single TTS call |
| Profile | YAML description of a listener and how to write and speak for them |
| Backend | A TTS engine implementation behind the TTSBackend interface |
| Voice | A built-in backend voice or a registered cloned voice with consent record |
| Take | One synthesis attempt for a chunk |
| Track | A final mastered audio file (child track, parent track, language track) |

---

### 1.2 `docs/ARCHITECTURE.md`

#### Required sections

1. System overview and diagram
2. Decision log (ADR-001 onward)
3. Package and module map
4. Data flow for `run`, `site`, `serve`, `mcp`
5. Data formats: Block JSON, Script Markdown, Profile YAML, Manifest JSON, Voice record
6. Contracts: CLI, Python API, REST API, MCP tools, TTSBackend, LLMProvider
7. Caching model
8. Error model
9. Security model
10. Deployment topologies

#### System overview (include this diagram)

```
                   +---------------------------------------------------------------+
  URL / file ----> |  1 FETCH+EXTRACT  ->  2 SCRIPT  ->  3 SYNTH  ->  4 MASTER  ->  5 PUBLISH |
                   |   fetch.py             script/       tts/         master/       publish/   |
                   |   extract.py           (LLM +        (backend,    (ffmpeg,      (mp3, vtt, |
                   |                         profile,     chunks,      loudnorm,     manifest,  |
                   |                         validate,    QA)          ID3)          embed,     |
                   |                         translate)                              inject)    |
                   +-------------^------------------^-------------------------------------------+
                                 |                  |
                          LLMProvider          TTSBackend
                    ollama | anthropic |   maya2 | kokoro | openai |
                      openai_compat        openai_compat | mock
                                 \                  /
                                  +-- cache/ (content-addressed) --+

  Front doors:  CLI (typer)  |  Python API  |  REST (FastAPI)  |  MCP (stdio/HTTP)  |  Studio UI  |  GitHub Action
```

#### Decision log (minimum ADRs)

```
ADR-001  Core language is Python 3.12, not Rust or TypeScript.
         Why: every viable open TTS model (Maya 2 Native, Kokoro, Chatterbox) ships Python
         inference code on PyTorch; a Rust or TS core would wrap Python anyway.
         Consequence: Python coding standards replace the Rust standards in this prompt.
ADR-002  CLI-first, no desktop shell in v1.
         Why: the flagship user is an engineer automating a static site; the Studio web UI on
         localhost covers interactive review without a Tauri bundle.
ADR-003  Default TTS backend is Maya 2 Native (Apache 2.0) via its OpenAI-compatible endpoint.
         Why: zero-shot cloning from 3 to 10 s of reference audio, English plus 11 Indian
         languages with cross-lingual cloning, permissive license, streaming support.
         Consequence: no inline emotion tags; expressiveness is carried by script wording,
         punctuation, pauses, and rate.
ADR-004  One OpenAI-compatible backend class serves Maya 2 server, OpenAI cloud, and any other
         compatible server; model-specific behavior lives in small adapters.
ADR-005  Synthesis is per chunk (2 to 4 sentences, max 400 chars default).
         Why: long inputs make TTS drift in timbre and pacing; per-chunk enables caching,
         retries, QA, and single-paragraph re-render.
ADR-006  Scripts are stored as human-editable Markdown, separate from audio.
         Why: the author must be able to review and edit before rendering (US-003, US-004).
ADR-007  Content-addressed cache keyed on normalized content plus all inputs that affect output.
ADR-008  Mastering uses ffmpeg via subprocess with argument arrays (never shell strings);
         pydub only for in-memory joins.
ADR-009  Player is a dependency-free web component with a native <audio> fallback.
ADR-010  Voice cloning requires a consent record; enforced in core, not just CLI.
ADR-011  LLM provider default is Ollama (local); Anthropic and OpenAI-compatible optional.
ADR-012  Server uses FastAPI with an in-process job queue (asyncio + one GPU worker) in v1;
         Redis-backed queue deferred.
ADR-013  MCP server uses the official Python MCP SDK; harness integrations ride on it.
ADR-014  Kokoro is the CPU fallback backend; Chatterbox optional extra; XTTS and F5-TTS are
         excluded by default because their weights are non-commercial.
```

#### Module map

```
audio_smith/
  __init__.py          version via importlib.metadata
  cli.py               typer app: run, script, render, inject, site, voice, profile,
                       doctor, studio, serve, mcp, cache
  config.py            pydantic-settings; env prefix AUDIO_SMITH_
  fetch.py             httpx fetch, size/time limits, scheme allowlist
  extract.py           selectolax DOM walk -> Block list; trafilatura fallback
  blocks.py            Block model, normalization, hashing
  profiles/            loader.py, schema.py, builtin/*.yaml
  script/              writer.py (LLM prompt build), validate.py, translate.py,
                       markdown.py (Script Markdown parse/serialize), lexicon.py
  llm/                 base.py (LLMProvider), ollama.py, anthropic.py, openai_compat.py, fake.py
  tts/                 base.py (TTSBackend, Capabilities), maya2.py, kokoro.py,
                       openai_compat.py, mock.py, registry.py
  voices/              registry.py, consent.py, clipcheck.py
  qa/                  similarity.py (speaker embeddings), loudness.py
  master/              assemble.py, ffmpeg.py, stings.py, tags.py
  publish/             manifest.py, vtt.py, embed.py, inject.py
  cache/               store.py, keys.py
  site.py              index crawl + batch
  server/              app.py (FastAPI), jobs.py, auth.py, models.py
  mcp_server/          server.py, tools.py
  studio/              routes.py, static/ (built from web/studio)
  doctor.py
player/                TypeScript web component <audio-smith-player>
web/studio/            Studio UI (TypeScript + Vite, no framework or Preact)
integrations/pi/       @mr-audio-smith/pi-extension (TypeScript)
integrations/goose/    toolkit.yaml
integrations/opencode/ config snippet
action/                composite GitHub Action
```

#### Data formats

**Block JSON** (`{slug}.blocks.json`)

```json
{
  "schema": "audio-smith/blocks@1",
  "source": "https://www.aadhish.us/letter-calm-in-the-chaos.html",
  "title": "The Calm Eye of the Storm",
  "lang": "en",
  "blocks": [
    {"id": "b001", "type": "title", "text": "The Calm Eye of the Storm", "track": "main"},
    {"id": "b002", "type": "paragraph", "text": "My dear Aadi, some days feel like ...", "track": "main"},
    {"id": "b010", "type": "list_item", "index": 2, "heading": "Find the calm eye of the storm",
     "text": "A hurricane is wild and windy ...", "track": "main"},
    {"id": "b020", "type": "paragraph", "text": "Not every kind of chaos is fun ...", "track": "parent"},
    {"id": "b024", "type": "signature", "text": "Your calm spot in every storm, Dad", "track": "main",
     "verbatim": true}
  ]
}
```

**Script Markdown** (`{slug}.{lang}.script.md`)

```markdown
---
schema: audio-smith/script@1
source: https://www.aadhish.us/letter-calm-in-the-chaos.html
profile: kid-5@1.0.0
lang: en
content_hash: 9f2c...e1
generated_by: ollama/qwen3:14b
---

## 001
My dear Aadi... [pause 600]
Some days feel like a big, swirly storm!

## 002
Toys everywhere. Everyone talking at once. [pause 400] And today is Halloween, too!

## 003 {verbatim}
Your calm spot in every storm, Dad.
```

Rules: `## NNN` starts a chunk; `{verbatim}` marks chunks the LLM must not change; the only inline markers are `[pause N]` (milliseconds, 100 to 3000) and `*word*` (gentle emphasis, rendered by backend-specific adapters or ignored). Nothing else is allowed.

**Profile YAML** (`profiles/kid-5.yaml`)

```yaml
id: kid-5
version: 1.0.0
description: A five-year-old listener, bedtime or car ride
audience:
  age: 5
  attention_minutes: 6
writing:
  target_minutes: 5
  max_sentence_words: 12
  explain_big_words: true
  spoken_transitions: true        # "Idea number two..."
  interactive_moments: 2          # "Let's breathe together"
  keep_signature_verbatim: true
  forbidden: [sarcasm, scary_detail, brand_names_without_context]
speech:
  rate: 0.9
  pause_after_heading_ms: 800
  pause_between_chunks_ms: 350
  max_chunk_chars: 360
languages: [en]                   # add "hi", "mr", "ta" for extra tracks
tracks:
  parent: adult-brief
mastering:
  intro_sting: builtin:chime-soft
  outro_sting: builtin:chime-soft
  music_bed: null                 # path or builtin id; ducked under voice
lexicon:
  Aadi: AH-dee
  Houston: HYOO-stun
```

**Voice record** (`voices/dad/voice.yaml`, clip at `voices/dad/reference.wav`)

```yaml
id: dad
display_name: Dad
backend_hints: [maya2]
reference: reference.wav
reference_text: "My dear Aadi, some days feel like a big swirly storm."
consent:
  speaker_name: Mohinish Shaikh
  relationship: self              # self | written_permission
  statement: "This is my own voice. I consent to mr-audio-smith cloning it for narration."
  date: 2026-11-01
clipcheck:
  duration_s: 9.4
  sample_rate: 24000
  snr_db: 34.1
  clipping_pct: 0.0
```

**Manifest JSON** (`{slug}.manifest.json`): schema id `audio-smith/manifest@1`, fields: tool version, source, title, profile id and version, backend id and model, voice id, content hash, created_at, tracks (lang, kind main or parent, file, duration_s, loudness_lufs, true_peak_dbtp), chunks (id, hash, take, seed, similarity, duration_ms), stage timings, warnings. Publish the JSON Schema at `schemas/manifest.schema.json`.

#### Contracts

**CLI** (document every command with flags, defaults, exit codes)

```
mr-audio-smith run <url|file> [--profile kid-5] [--voice dad] [--backend maya2]
                    [--lang en,hi] [--out ./audio] [--inject page.html]
                    [--llm ollama:qwen3:14b] [--approve] [--force] [--dry-run]
mr-audio-smith script <url|file> [--profile] [--out]          # stages 1-2 only
mr-audio-smith render <script.md> [--chunks 3,7] [--voice] [--backend] [--out]
mr-audio-smith inject <page.html> --manifest <file> [--selector "h1"] [--dry-run]
mr-audio-smith site <index-url> --match "letter-*.html" [--max-pages 50] [run flags]
mr-audio-smith voice add <id> --clip <wav> --name <speaker> --relationship self
mr-audio-smith voice list | check <id> | remove <id>
mr-audio-smith profile list | show <id> | validate <file>
mr-audio-smith doctor [--json]
mr-audio-smith studio [--port 7341]
mr-audio-smith serve [--host 127.0.0.1] [--port 7340]
mr-audio-smith mcp [--transport stdio|http]
mr-audio-smith cache info | prune --older-than 30d
Exit codes: 0 ok, 2 usage, 3 preflight failed, 4 extract failed, 5 script invalid,
            6 synthesis failed, 7 mastering failed, 8 consent missing
```

**TTSBackend** (Python protocol)

```python
class Capabilities(BaseModel):
    languages: list[str]
    cloning: bool
    builtin_voices: list[str]
    sample_rate: int
    max_chars: int
    streaming: bool
    license: str
    commercial_ok: bool

class TTSBackend(Protocol):
    id: str
    def capabilities(self) -> Capabilities: ...
    def preflight(self) -> list[PreflightIssue]: ...
    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio: ...
```

**LLMProvider**

```python
class LLMProvider(Protocol):
    id: str
    def preflight(self) -> list[PreflightIssue]: ...
    def complete(self, system: str, user: str, *, temperature: float, seed: int | None,
                 max_tokens: int) -> str: ...
```

**REST API** (FastAPI, prefix `/v1`)

```
POST /v1/jobs                  body: {source, profile, voice, backend, langs, options}
                               -> 202 {job_id}
GET  /v1/jobs/{id}             -> {status: queued|running|done|failed, stage, progress, error}
GET  /v1/jobs/{id}/manifest    -> manifest JSON
GET  /v1/jobs/{id}/files/{name}-> audio, vtt, embed
POST /v1/scripts               -> generate script only
POST /v1/render                -> render a provided script (optionally subset of chunks)
GET  /v1/voices | /v1/profiles | /v1/backends
GET  /healthz (liveness) | /readyz (backend + model loaded)
```

**MCP tools**: see Appendix E.

#### Caching model

```
cache/
  v1/
    blocks/{content_hash}.json
    scripts/{script_key}.md            script_key = H(content_hash, profile@ver, llm, lang)
    chunks/{chunk_key}.wav             chunk_key  = H(chunk_text_after_lexicon, backend,
                                                     model, voice_id, voice_clip_hash,
                                                     rate, seed)
    tracks/{track_key}.mp3
```

#### Error model

Every failure raises a typed `AudioSmithError` subclass with `code`, `stage`, `message`, `hint`. CLI maps codes to exit codes. Server maps to RFC 9457 problem+json. Never print stack traces to users unless `--debug`.

#### Security model

Covered in full in the Security Guidelines section of this prompt; ARCHITECTURE.md must summarize it: fetch scheme allowlist and SSRF guard (block private and link-local IP ranges unless `--allow-private`), HTML never executed, subprocess argument arrays only, localhost binding defaults, bearer token for non-localhost server, consent enforcement, no secrets in manifests, path traversal guard on all file names derived from URLs.

#### Deployment topologies

1. Laptop or workstation: CLI + local Maya 2 server or in-process.
2. GPU box on LAN (for example a DGX Spark class machine): `mr-audio-smith serve` + Maya 2 server; static-site CI calls it.
3. Kubernetes: Helm chart (Appendix G).

---

### 1.3 `docs/DESIGN.md`

mr-audio-smith has two visual surfaces: the **embed player** (seen by listeners, including five-year-olds) and the **Studio** review UI (seen by authors). DESIGN.md must specify both using the Design System section of this prompt as the minimum, plus:

- Player states: idle, loading, playing, paused, ended, error, offline; captions on and off; language toggle; kid size variant (`size="kid"`) with an 64px play button.
- Player wireframe (ASCII) for default and kid variants.
- Studio wireframes: script editor with chunk list, chunk detail with take comparison, render queue, approve and publish panel.
- Component inventory with every component, its props, and states.
- Motion rules: one waveform "breathing" animation while playing, disabled under prefers-reduced-motion.
- Copy guidelines: player label defaults to "Listen"; author can override (for example "Listen to Dad read this letter").
- Anti-patterns list (see Design System section).

Player wireframe (include):

```
Default
+--------------------------------------------------------------+
|  (>)   Listen to Dad read this letter          4:12   [CC] [EN|HI] |
|        |||||||.|||||.||||||||||||..|||||                       |
+--------------------------------------------------------------+

Kid variant (size="kid")
+----------------------------------------+
|                                        |
|      (  >  )     Listen to Dad         |
|     64px btn     big friendly label    |
|  [=========o-----------------]  4:12   |
+----------------------------------------+
```

---

### 1.4 `docs/SPRINT_PLAN.md`

Copy every sprint and every task from the sprint sections of this prompt (Sprints 0 to 6) and Appendices C to G (Sprints 7 to 9) into SPRINT_PLAN.md, with task IDs, titles, labels, descriptions, acceptance criteria, estimates (S = half day, M = 1 day, L = 2 days, XL = 3+ days, split XL before starting), and dependencies. Include the sprint overview table from Appendix H and a dependency graph:

```
S0 Scaffold -> S1 Extract+Script -> S2 Voices -> S3 Synthesis+Mastering (core)
                                                     |
                                    S4 Publish+Site <+> S5 Studio
                                                     |
                                                 S6 Release v1.0.0
                                                     |
                                    S7 Server+MCP -> S8 Harnesses -> S9 Packaging
```

---

### 1.5 `docs/TEST_PLAN.md`

#### Required sections

1. Strategy and test pyramid
2. Coverage targets (mirror `.coverage-thresholds.toml`)
3. Naming convention
4. Fixtures and golden files
5. Scenario tables per feature area (status column: ✅ Automated, ⚠️ Deferred, ❌ Skipped with reason)
6. Listening test protocol (human evaluation)
7. Smoke checklist for staging
8. Regression policy

#### Strategy

- **Unit** (pytest): pure logic: extraction rules, block normalization, hashing, profile validation, script parse and validate, lexicon, VTT timing math, cache keys, inject idempotence, consent rules.
- **Integration** (pytest -m integration): real ffmpeg, real Ollama with a small model, real Kokoro on CPU, Maya 2 server when `AUDIO_SMITH_IT_MAYA2_URL` is set (GPU runner).
- **Golden audio tests**: mock backend produces deterministic tones per character; mastering output compared by duration, loudness, and chunk boundary timestamps within tolerance (never byte equality for encoded audio).
- **Smoke**: `tests/smoke/smoke.sh` runs `doctor`, then `run` on `tests/fixtures/pages/letter-calm.html` with the mock LLM and mock TTS, asserts outputs exist and manifest validates.
- **E2E** (Playwright): player component (keyboard, captions, language toggle, no-JS fallback) and Studio flows.
- **Regression**: one test per fixed bug, never deleted.
- **Listening tests** (manual, per release): 3 fixture letters, kid-5 profile, cloned voice; rubric scored 1 to 5 on warmth, clarity, pacing, pronunciation, consistency, script faithfulness. Release blocked if any average under 4.

#### Naming convention

```
Unit:        test_{module}_{function}_{scenario}_{expected_outcome}
Integration: it_{component}_{operation}_{scenario}
Smoke:       smoke_{feature}_{minimal_assertion}
E2E:         e2e_{user_story_id}_{scenario}
Regression:  regression_{gh_issue_number}_{what_was_broken}
```

#### Fixtures

```
tests/fixtures/
  pages/letter-calm.html          saved copy of the reference letter (author's own content)
  pages/index-messages.html       saved copy of the letters index page
  pages/data-narrate.html         page using data-narrate attributes, skip and parent tracks
  pages/hostile.html              scripts, iframes, giant inline base64, 3 MB of text
  scripts/valid.script.md
  scripts/invalid-markers.script.md
  profiles/custom-commute.yaml
  voices/clean.wav                synthetic tone clip with consent record
  voices/clipped.wav | noisy.wav | too-short.wav
  llm/                            recorded LLM responses for the fake provider
```

#### Minimum scenario tables (expand per feature)

| ID | Scenario | Type | Status |
|---|---|---|---|
| test_extract_blocks_data_narrate_present_uses_only_marked_element | Extraction honors [data-narrate] | Unit | ⚠️ |
| test_extract_blocks_emoji_stripped | Emoji never reach blocks | Unit | ⚠️ |
| test_extract_blocks_skip_attribute_excluded | data-narrate="skip" excluded | Unit | ⚠️ |
| test_extract_blocks_parent_attribute_routed | Parent track routing | Unit | ⚠️ |
| test_blocks_hash_whitespace_change_stable | Hash ignores whitespace | Unit | ⚠️ |
| test_blocks_hash_text_change_differs | Hash detects text edits | Unit | ⚠️ |
| test_profiles_load_invalid_rate_rejected | Schema errors are clear | Unit | ⚠️ |
| test_script_validate_unknown_marker_rejected | Validator rejects invented tags | Unit | ⚠️ |
| test_script_validate_verbatim_chunk_changed_rejected | Verbatim enforced | Unit | ⚠️ |
| test_script_writer_retry_with_violations_succeeds | One corrective retry | Unit | ⚠️ |
| test_lexicon_apply_whole_word_only | "Aadi" replaced, "Aadish" not | Unit | ⚠️ |
| test_translate_preserves_chunk_count_and_pauses | Translation alignment | Unit | ⚠️ |
| test_consent_clone_unregistered_voice_raises | Consent enforced in core | Unit | ⚠️ |
| test_clipcheck_too_short_rejected | Clip quality gate | Unit | ⚠️ |
| test_qa_similarity_below_threshold_rerenders | QA retake loop | Unit | ⚠️ |
| test_master_loudness_within_target | -16 LUFS plus or minus 1 | Integration | ⚠️ |
| test_vtt_cues_align_within_150ms | Caption alignment | Unit | ⚠️ |
| test_inject_idempotent_second_run_no_diff | Inject idempotence | Unit | ⚠️ |
| test_inject_outside_markers_untouched | Inject safety | Unit | ⚠️ |
| test_fetch_private_ip_blocked | SSRF guard | Unit | ⚠️ |
| test_cache_unchanged_page_skips_render | Incremental build | Unit | ⚠️ |
| it_maya2_synth_clone_returns_24khz_mono | Maya 2 integration | Integration | ⚠️ |
| it_kokoro_synth_cpu_returns_audio | Kokoro integration | Integration | ⚠️ |
| it_ollama_script_kid5_within_length | Real LLM script length | Integration | ⚠️ |
| smoke_run_mock_outputs_exist | End to end with mocks | Smoke | ⚠️ |
| e2e_US006_player_keyboard_play_pause | Player keyboard | E2E | ⚠️ |
| e2e_US012_player_captions_toggle | Captions | E2E | ⚠️ |
| e2e_US017_studio_compare_takes_keep_best | Studio takes | E2E | ⚠️ |
| e2e_US006_player_no_js_fallback_plays | No-JS fallback | E2E | ⚠️ |

---
## Step 2: GitHub Project Setup

### 2.1 Repository initialization

```bash
gh repo create mohnishbasha/mr-audio-smith \
  --public \
  --description "Turn any web page into a realistic, audience-tuned narration with your own cloned voice, generated locally, embedded with one tag." \
  --homepage "https://getaudiosmith.com" \
  --license mit \
  --gitignore Python
git clone git@github.com:mohnishbasha/mr-audio-smith.git && cd mr-audio-smith
# Replace the generated .gitignore with the one specified in Sprint 0 (S0-T03)
git checkout -b develop && git push -u origin develop
git checkout -b staging && git push -u origin staging
gh repo edit --default-branch develop
gh repo edit --enable-issues --enable-projects --enable-wiki=false \
  --delete-branch-on-merge --enable-squash-merge --enable-merge-commit=false \
  --enable-rebase-merge=false
gh repo edit --add-topic tts,text-to-speech,narration,voice-cloning,maya2,accessibility,local-first,python,mcp,snackonai
```

### 2.2 Branch protection

```bash
# main: production releases only
gh api -X PUT repos/mohnishbasha/mr-audio-smith/branches/main/protection \
  -f required_status_checks.strict=true \
  -f 'required_status_checks.contexts[]=lint-and-typecheck' \
  -f 'required_status_checks.contexts[]=unit-tests' \
  -f 'required_status_checks.contexts[]=coverage' \
  -f 'required_status_checks.contexts[]=integration-tests' \
  -f 'required_status_checks.contexts[]=e2e-tests' \
  -f 'required_status_checks.contexts[]=check-versions' \
  -F enforce_admins=true \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F required_pull_request_reviews.dismiss_stale_reviews=true \
  -F restrictions=null -F allow_force_pushes=false -F allow_deletions=false \
  -F required_linear_history=true

# staging: 1 approval, same checks
# develop: CI required (lint-and-typecheck, unit-tests, coverage), no approval required
```

### 2.3 Git branch strategy

```
main      -> production releases only, protected, requires 1+ approvals
staging   -> staging environment, requires 1 approval
develop   -> integration branch, all feature work merges here
feature/* -> off develop
fix/*     -> off develop (or main for hotfixes)
chore/*   -> non-functional changes
docs/*    -> documentation only
```

Rules:
- No direct commits to `main` or `staging`. Ever.
- All PRs require passing CI before merge.
- Hotfixes branch from `main`, merge to `main` and back-merge to `develop`.
- `main` tagged for every release using semantic versioning.

### 2.4 Label taxonomy (create all 44)

```bash
create() { gh label create "$1" --color "$2" --description "$3" --force; }

# type
create "type: feature"      "1D76DB" "New user-facing capability"
create "type: bug"          "D73A4A" "Something is broken"
create "type: chore"        "C5DEF5" "Tooling, deps, maintenance"
create "type: docs"         "0075CA" "Documentation only"
create "type: test"         "BFD4F2" "Test infrastructure or coverage"
create "type: refactor"     "D4C5F9" "No behavior change"
create "type: perf"         "FBCA04" "Performance"
create "type: security"     "B60205" "Security hardening or fix"
create "type: spec"         "5319E7" "Spec document change"
create "enhancement"        "A2EEEF" "Deferred or future improvement"

# area
create "area: fetch"        "0E8A16" "Fetching pages"
create "area: extract"      "0E8A16" "Content extraction and blocks"
create "area: profiles"     "0E8A16" "Audience profiles"
create "area: script"       "0E8A16" "Script writing, validation, translation"
create "area: llm"          "0E8A16" "LLM providers"
create "area: tts"          "0E8A16" "TTS backends"
create "area: voices"       "0E8A16" "Voice registry, consent, clip checks"
create "area: qa"           "0E8A16" "Speaker similarity and audio QA"
create "area: master"       "0E8A16" "Mastering and encoding"
create "area: publish"      "0E8A16" "Manifest, VTT, embed, inject"
create "area: player"       "0E8A16" "Web component player"
create "area: studio"       "0E8A16" "Studio review UI"
create "area: cli"          "0E8A16" "Command line"
create "area: server"       "0E8A16" "REST server"
create "area: mcp"          "0E8A16" "MCP server"
create "area: harness"      "0E8A16" "Pi, Goose, OpenCode, Claude Code"
create "area: action"       "0E8A16" "GitHub Action"
create "area: packaging"    "0E8A16" "Docker, Helm, PyPI, npm"
create "area: ci"           "0E8A16" "GitHub Actions workflows"

# priority
create "priority: p0"       "B60205" "Blocks the sprint gate"
create "priority: p1"       "D93F0B" "Must ship this sprint"
create "priority: p2"       "FBCA04" "Should ship this sprint"
create "priority: p3"       "C2E0C6" "Nice to have"

# status
create "status: blocked"    "000000" "Waiting on a dependency"
create "status: needs-spec" "5319E7" "Spec must be updated first"
create "status: in-review"  "FEF2C0" "PR open"

# size
create "size: S"            "EDEDED" "Half day"
create "size: M"            "D4D4D4" "One day"
create "size: L"            "BDBDBD" "Two days"
create "size: XL"           "9E9E9E" "Three+ days, split before starting"

# sprint
for n in 0 1 2 3 4 5 6 7 8 9; do create "sprint: $n" "F9D0C4" "Sprint $n"; done
```

### 2.5 Milestones

```bash
ms() { gh api repos/mohnishbasha/mr-audio-smith/milestones -f title="$1" -f description="$2" -f due_on="$3"; }
ms "Sprint 0: Scaffold"                "Tooling, CI, agent files, empty CLI, spec docs committed"        "2026-11-09T23:59:59Z"
ms "Sprint 1: Extract and Script"      "Fetch, extract, profiles, LLM providers, script writer+validator" "2026-11-16T23:59:59Z"
ms "Sprint 2: Voices and Backends"     "TTSBackend, Maya 2, Kokoro, OpenAI, mock, voice registry+consent" "2026-11-23T23:59:59Z"
ms "Sprint 3: Synthesis and Mastering" "Chunked synthesis, QA, mastering, cache, manifest, VTT, run cmd"  "2026-12-07T23:59:59Z"
ms "Sprint 4: Publish and Site"        "Player, embed, inject, translation, site batch, GitHub Action"   "2026-12-14T23:59:59Z"
ms "Sprint 5: Studio"                  "Local review UI: edit script, render chunks, compare takes"      "2026-12-21T23:59:59Z"
ms "Sprint 6: Release v1.0.0"          "Docs, hardening, listening tests, PyPI + npm, v1.0.0"            "2026-12-28T23:59:59Z"
ms "Sprint 7: Server and MCP"          "REST server with jobs, MCP server (stdio + HTTP)"                "2027-01-04T23:59:59Z"
ms "Sprint 8: Harness Integrations"    "Pi extension, Goose toolkit, OpenCode, Claude Code skill"        "2027-01-11T23:59:59Z"
ms "Sprint 9: Packaging"               "Docker (CUDA, CPU, arm64), Compose, Helm, cosign"                "2027-01-18T23:59:59Z"
```

Adjust due dates to the actual start date; keep the relative durations (Sprint 3 is two weeks).

### 2.6 Project board

```bash
gh project create --owner mohnishbasha --title "mr-audio-smith"
```

Columns (single-select Status field): **Backlog, Ready, In Progress, In Review, Done**. Custom fields: Sprint (single select 0 to 9), Size (S, M, L, XL), Priority (p0 to p3).

Automation rules:
- Issue added to repo -> Backlog
- Issue assigned and branch linked -> In Progress
- PR opened referencing issue -> In Review
- PR merged / issue closed -> Done
- Issue reopened -> In Progress

### 2.7 Templates

`.github/ISSUE_TEMPLATE/task.yml`

```yaml
name: Task
description: A sprint task from docs/SPRINT_PLAN.md
title: "[S{sprint}-T{nn}] "
labels: []
body:
  - type: input
    id: task_id
    attributes: {label: Task ID, placeholder: S3-T04}
    validations: {required: true}
  - type: textarea
    id: description
    attributes: {label: Description}
    validations: {required: true}
  - type: textarea
    id: acceptance
    attributes: {label: Acceptance criteria, description: Checklist, value: "- [ ] "}
    validations: {required: true}
  - type: input
    id: spec_refs
    attributes: {label: Spec references, placeholder: "PRD FR-012, ARCHITECTURE ADR-005"}
  - type: input
    id: depends
    attributes: {label: Depends on, placeholder: "#12, #14"}
  - type: textarea
    id: tests
    attributes: {label: Test scenarios (TEST_PLAN ids)}
```

`.github/ISSUE_TEMPLATE/bug.yml`

```yaml
name: Bug report
description: Something is broken
labels: ["type: bug"]
body:
  - type: textarea
    id: what
    attributes: {label: What happened}
    validations: {required: true}
  - type: textarea
    id: repro
    attributes: {label: Steps to reproduce (command, page URL or fixture, profile, backend)}
    validations: {required: true}
  - type: textarea
    id: expected
    attributes: {label: Expected}
  - type: textarea
    id: doctor
    attributes: {label: Output of `mr-audio-smith doctor --json`, render: json}
  - type: input
    id: version
    attributes: {label: Version (`mr-audio-smith --version`)}
```

`.github/PULL_REQUEST_TEMPLATE.md`

```markdown
## Summary
Closes #

## Spec impact (choose one)
- [ ] A: Internal only, no spec change
- [ ] B: Spec updated in this PR: (list docs/ sections)
- [ ] C: Spec issue filed: #

## Tests
- [ ] Failing tests written first (TDD)
- [ ] TEST_PLAN.md scenarios added/marked ✅
- [ ] Coverage thresholds hold

## Checklist
- [ ] `make lint` exits 0
- [ ] `make typecheck` exits 0
- [ ] `make test` exits 0
- [ ] CHANGELOG.md [Unreleased] updated (if user-facing)
- [ ] No em dashes added in prose or comments
```

---

## Step 3: Create All GitHub Issues

### 3.1 Issue creation protocol

For every task in `docs/SPRINT_PLAN.md`:

1. Title: `[S{n}-T{nn}] {Imperative title}` (example: `[S3-T04] Implement speaker similarity QA with retakes`).
2. Body: use the Task template fields. Copy description and acceptance criteria verbatim from SPRINT_PLAN.md. Fill spec references and TEST_PLAN scenario ids.
3. Labels: one `type:`, one or more `area:`, one `priority:`, one `size:`, one `sprint:`.
4. Milestone: the sprint milestone.
5. Add to the project board in Backlog with Sprint, Size, Priority fields set.
6. After all issues exist, edit bodies to replace task-id dependencies (`S2-T03`) with issue numbers (`#23`).

Script it:

```bash
# scripts/create-issues.py reads docs/SPRINT_PLAN.md (parse the task tables) and calls
# `gh issue create` per task, then `gh project item-add`. Commit the script.
python scripts/create-issues.py --dry-run   # review
python scripts/create-issues.py
```

### 3.2 Implementation comment protocol

Before closing any issue, add a comment:

```markdown
### Implementation
- **PR:** #NN
- **What changed:** (2 to 5 bullets)
- **Spec sections updated:** (or "none, internal only")
- **Tests added:** unit N, integration N, e2e N (list names)
- **Coverage delta:** core 86.1% -> 87.4%
- **Follow-ups:** (new issues created, with numbers)
```

### 3.3 Issue closing protocol

An issue closes only when: its PR is merged into `develop`, every acceptance criterion is checked, the implementation comment exists, and its TEST_PLAN scenarios are ✅ or ❌ with reason. Issues are closed by the merge (`Closes #NN`) or manually after the comment, never before.

---

## Step 4 onward: Sprint Execution

### Sprint Start Protocol
1. Move all sprint issues from Backlog to In Progress on the project board
2. Assign issues to yourself
3. Pull latest `develop`, verify it is up to date with `staging`
4. Pick the highest-priority unblocked issue
5. Read the relevant PRD, ARCHITECTURE, and TEST_PLAN sections before writing code
6. Add test scenarios for this feature to `docs/TEST_PLAN.md` before writing code
7. Create a branch: `git checkout -b feature/s{n}-t{nn}-{short-slug} develop`
8. Write failing tests first (TDD), confirm they fail for the right reason
9. Implement until tests pass
10. Update `docs/TEST_PLAN.md` to mark new scenarios as ✅ Automated
11. Update relevant spec doc in the same branch if behavior changed
12. Open PR against `develop`; PR description must state which spec sections updated
13. Wait for CI (lint + type-check + unit + integration + coverage threshold)
14. Merge
15. Add implementation comment and close issue
16. Pick next issue

**TDD is mandatory.** No production code is written without a failing test that requires it. The only exceptions are pure configuration files and generated code, and the PR must say so.

### Spec Change Protocol
Any PR that changes user-facing behavior, API contracts, file formats, CLI flags, profile schema, or architectural decisions must satisfy one of:

- **A: No spec change:** PR description explicitly states "internal only, no spec change" and reviewer agrees
- **B: Spec updated in same PR:** Relevant `docs/` file updated alongside code
- **C: Spec issue filed:** Separate GitHub issue created before code PR merges, scheduled in current sprint, closed within same sprint

Option C is not a deferral mechanism.

Spec docs are living documents. Every PR that changes behavior updates the relevant spec doc in the same commit.

### Test Scenario Generation Protocol
1. Open `docs/TEST_PLAN.md` and add scenarios for the feature before writing code
2. Use naming convention: `{type}_{module}_{operation}_{scenario}_{outcome}`
3. Mark new scenarios as ⚠️ Deferred until test written, then ✅ Automated
4. Scenarios too hard to automate: ❌ Skipped with written reason and manual step
5. Test file must have a test for every ✅ scenario when feature PR merges

### Sprint End Protocol
1. All sprint issues closed or moved to next sprint with explanation
2. Run full sprint gate checklist
3. Spec doc audit: review all five docs for stale sections, update before proceeding
4. Coverage check: `make coverage` (pytest-cov + vitest --coverage), confirm meets targets
5. Merge `develop` into `staging` via PR
6. Run manual smoke tests on staging using TEST_PLAN.md smoke checklist
7. Document sprint retrospective in `docs/RETROSPECTIVES.md`:
   - What was built (link to closed issues)
   - Spec sections updated
   - Tests added (counts by type)
   - Coverage delta
   - What worked, what didn't, what to change
8. Tag staging build: `git tag sprint-{n}-complete && git push origin sprint-{n}-complete`

### Definition of Done

A feature is done when:
- [ ] Code implemented and runs without errors
- [ ] Unit tests written and passing
- [ ] `make lint` exits 0 with 0 warnings (ruff, eslint)
- [ ] `make typecheck` exits 0 (mypy --strict, tsc --noEmit)
- [ ] Coverage has not dropped below thresholds
- [ ] PR opened against `develop` with issue linked
- [ ] CI green on all 3 platforms (ubuntu, macos, windows-wsl smoke)
- [ ] Spec doc changes committed in same PR (or Option A/C confirmed)
- [ ] New test scenarios added to TEST_PLAN.md
- [ ] Implementation comment added to issue before closing

### Regression Test Lifecycle

```
Bug reported -> GitHub issue created (type: bug label)
      |
Reproduction confirmed -> regression test written (FAILS)
      |
Fix implemented -> regression test passes
      |
PR opened: regression test + fix in same commit
      |
PR merged -> issue closed -> test runs in CI forever
```

Regression tests are never deleted.

---
## Sprint 0: Scaffold

**Milestone:** Sprint 0: Scaffold
**Duration:** 1 week
**Goal:** A repository where `mr-audio-smith --version` and `mr-audio-smith doctor` run, CI is green on all platforms, every agent file exists, and nothing product-specific is implemented yet.

### S0-T01: Commit the five spec documents
- **Labels:** type: spec, area: ci, priority: p0, size: L, sprint: 0
- **Description:** Generate PRD, ARCHITECTURE, DESIGN, SPRINT_PLAN, TEST_PLAN per Step 1. This task is completed before Step 2 and recorded retroactively as an issue.
- **AC:**
  - [ ] All five files exist under `docs/` with every required section
  - [ ] Every FR has acceptance criteria; every US maps to at least one FR
  - [ ] Committed as the first commit on `main`
- **Depends on:** none

### S0-T02: Python project skeleton with uv
- **Labels:** type: chore, area: cli, priority: p0, size: M, sprint: 0
- **Description:** Create `pyproject.toml` (hatchling build backend, Python `>=3.12,<3.14`), `uv.lock`, `audio_smith/` package with `__init__.py` reading version via `importlib.metadata`, typer CLI with `--version`. Optional dependency groups: `maya2`, `kokoro`, `chatterbox`, `cloud`, `server`, `mcp`, `qa`, `dev`.
- **AC:**
  - [ ] `uv sync --all-extras --dev` succeeds on macOS arm64 and Linux x86_64
  - [ ] `uv run mr-audio-smith --version` prints the version from `pyproject.toml`
  - [ ] Base install (no extras) does not pull torch
- **Depends on:** S0-T01

### S0-T03: Repository hygiene files
- **Labels:** type: chore, area: ci, priority: p0, size: S, sprint: 0
- **Description:** `.gitignore`, `.editorconfig`, `.gitattributes` (mark `*.wav *.mp3 *.opus` as binary, LFS for `tests/fixtures/voices/*.wav` and `assets/stings/*`), `LICENSE` (MIT, Serverless Ventures LLC, 2026), `THIRD_PARTY_LICENSES.md` stub, `CHANGELOG.md` with `[Unreleased]`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` (with DCO sign-off requirement).
- **.gitignore must include:**
  ```
  # Python
  __pycache__/
  *.py[cod]
  .venv/
  dist/
  build/
  *.egg-info/
  .mypy_cache/
  .ruff_cache/
  .pytest_cache/
  # TypeScript / Node / Bun
  node_modules/
  *.tsbuildinfo
  player/dist/
  web/studio/dist/
  integrations/pi/dist/
  .bun/
  # Environment
  .env
  .env.*
  !.env.*.example
  # Test / coverage
  coverage/
  .coverage
  htmlcov/
  coverage.xml
  playwright-report/
  test-results/
  # Product runtime
  .audio-smith/cache/
  out/
  audio/
  *.db
  *.db-shm
  *.db-wal
  voices/*/reference.wav        # never commit real voice clips by default
  !tests/fixtures/voices/*.wav
  # Model weights
  models/
  *.safetensors
  *.bin
  *.gguf
  # Agent sessions
  .pi/sessions/
  .agent/sessions/
  CLAUDE.local.md
  # OS / editor
  .DS_Store
  Thumbs.db
  .vscode/settings.json
  .idea/
  # Lock files ARE tracked: uv.lock, bun.lockb, package-lock.json
  ```
- **AC:**
  - [ ] All files present; `voices/*/reference.wav` ignored; fixtures not ignored
- **Depends on:** S0-T02

### S0-T04: Lint, format, type-check toolchain
- **Labels:** type: chore, area: ci, priority: p0, size: S, sprint: 0
- **Description:** ruff (lint + format) with rules `E,F,W,I,N,UP,B,A,C4,SIM,RUF,S,PTH,TID,PL`, mypy `--strict`, pre-commit hooks (ruff, mypy, codespell, check-yaml, end-of-file-fixer, a custom hook rejecting em dash characters in `*.md *.py *.ts *.yaml`). `Makefile` targets: `lint`, `format`, `typecheck`, `test`, `test-int`, `coverage`, `smoke`, `e2e`, `check-versions`, `build`.
- **AC:**
  - [ ] `make lint typecheck` exit 0 on the skeleton
  - [ ] The em dash hook fails on a file containing the character U+2014
- **Depends on:** S0-T02

### S0-T05: Test harness and coverage thresholds
- **Labels:** type: test, area: ci, priority: p0, size: M, sprint: 0
- **Description:** pytest with `pytest-cov`, `pytest-asyncio`, `pytest-timeout`, `hypothesis`, `respx` (httpx mocking), `syrupy` (snapshots). Markers: `integration`, `gpu`, `slow`. Create `tests/{unit,integration,smoke,e2e,regression}/` and `tests/fixtures/` with the fixtures listed in TEST_PLAN. `.coverage-thresholds.toml` and `scripts/check-coverage.py` that fails CI when any module is under threshold.
- **AC:**
  - [ ] `make test` runs and reports coverage per package
  - [ ] Threshold script fails when a module falls under its target
- **Depends on:** S0-T04

### S0-T06: CI workflow
- **Labels:** type: chore, area: ci, priority: p0, size: M, sprint: 0
- **Description:** `.github/workflows/ci.yml` with jobs: `lint-and-typecheck` (ubuntu, macos, windows), `unit-tests` (matrix 3 OS x Python 3.12, 3.13), `coverage` (ubuntu, upload to Codecov), `integration-tests` (ubuntu, installs ffmpeg, Ollama with `qwen3:0.6b`, Kokoro CPU), `e2e-tests` (ubuntu, Playwright), `check-versions`, `smoke`. `gpu-integration` job runs only on `workflow_dispatch` and on PRs to `staging`/`main` against a self-hosted runner labeled `gpu` with Maya 2.
- **AC:**
  - [ ] All jobs green on the skeleton
  - [ ] Concurrency group cancels superseded runs
  - [ ] Dependabot configured for pip (uv), npm, github-actions, docker
- **Depends on:** S0-T05

### S0-T07: Version scripts
- **Labels:** type: chore, area: ci, priority: p1, size: S, sprint: 0
- **Description:** `scripts/check-versions.sh`, `scripts/extract-changelog.sh`, `scripts/bump-version.sh` exactly as specified in the Versioning section.
- **AC:**
  - [ ] `check-versions.sh` exits 1 naming the file when a version differs
  - [ ] `extract-changelog.sh 0.1.0` prints only that section
- **Depends on:** S0-T02

### S0-T08: Agent repository files
- **Labels:** type: docs, area: harness, priority: p0, size: M, sprint: 0
- **Description:** Create `AGENTS.md`, `CLAUDE.md`, `SKILLS.md`, `SOUL.md`, `.agent/skills/run-tests/{SKILL.md,run.sh}`, `.agent/skills/check-types/{SKILL.md,run.sh}`, `.agent/skills/narrate-fixture/{SKILL.md,run.sh}` with the content specified in Appendix K.
- **AC:**
  - [ ] `CLAUDE.md` first line is `@import AGENTS.md`
  - [ ] Both required skills run and exit 0 on the skeleton
  - [ ] SOUL.md has at least 6 hard constraints and no commands or paths
- **Depends on:** S0-T04, S0-T05

### S0-T09: Doctor command (skeleton)
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 0
- **Description:** `doctor.py` with a check registry; implement Python version, ffmpeg presence and version (>= 6.0), disk space, cache dir writable. Later sprints register backend, LLM, GPU, voice checks.
- **AC:**
  - [ ] Human table output and `--json` output
  - [ ] Exit 3 when a required check fails; every failure has a hint
- **Depends on:** S0-T02

### S0-T10: Config system
- **Labels:** type: feature, area: cli, priority: p1, size: S, sprint: 0
- **Description:** pydantic-settings `Settings` with env prefix `AUDIO_SMITH_`, project file `audio-smith.toml` discovered upward from cwd, CLI flags override env override file override defaults. Document precedence in ARCHITECTURE.
- **AC:**
  - [ ] Precedence covered by unit tests
  - [ ] Unknown keys in `audio-smith.toml` produce a warning, not a crash
- **Depends on:** S0-T02

### Sprint 0 Gate (hard stop)
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
- **Description:** httpx client with timeout, max bytes (streamed, abort over limit), redirect limit 5, scheme allowlist (`http`, `https`, `file` for local paths), SSRF guard resolving DNS and rejecting private, loopback, link-local, and metadata ranges unless `--allow-private`. Respect `Content-Type` and charset.
- **AC:** FR-001 ACs; `test_fetch_private_ip_blocked` and redirect-to-private case covered
- **Depends on:** S0-T10

### S1-T02: Block model and normalization
- **Labels:** type: feature, area: extract, priority: p0, size: S, sprint: 1
- **Description:** pydantic `Block`, `BlockDoc`; normalization (Unicode NFC, collapse whitespace, smart quotes to straight quotes for hashing only, strip emoji via the `emoji` package plus regional indicator ranges); `content_hash()` per FR-003.
- **AC:** FR-003 ACs; property tests with hypothesis for whitespace invariance
- **Depends on:** S0-T05

### S1-T03: Extractor
- **Labels:** type: feature, area: extract, priority: p0, size: L, sprint: 1
- **Description:** selectolax-based DOM walk implementing FR-002 order and rules. Map `h1` to title, `h2-h4` to heading, `p` to paragraph, `ol/ul > li` to list_item (index and nested heading captured), `blockquote` to quote, elements with `data-narrate-role="signature"` or a final short paragraph after the last heading starting with a sign-off pattern to signature. Remove nav, header, footer, aside, form, script, style, noscript, svg, button elements. Labels like "Something Dad believes" and "A grown-up note" are treated as headings; "A grown-up note" content goes to parent track only when marked `data-narrate="parent"` (no magic string matching in core; provide an opt-in profile rule `parent_headings: ["A grown-up note"]`).
- **AC:** FR-002 ACs; snapshot test on `letter-calm.html` matches expected block JSON; `hostile.html` handled within limits
- **Depends on:** S1-T02

### S1-T04: Profile schema, loader, built-ins
- **Labels:** type: feature, area: profiles, priority: p0, size: M, sprint: 1
- **Description:** pydantic schema for Profile YAML (ARCHITECTURE format); loader with precedence (project `./profiles` over built-in); built-ins `kid-5`, `kid-8`, `adult-commute`, `adult-brief`; `profile list|show|validate` commands; export JSON Schema to `schemas/profile.schema.json`.
- **AC:** FR-004 ACs; invalid profiles produce errors naming the field path
- **Depends on:** S0-T10

### S1-T05: LLM provider interface and providers
- **Labels:** type: feature, area: llm, priority: p0, size: L, sprint: 1
- **Description:** `LLMProvider` protocol; `OllamaProvider` (REST `/api/chat`, not subprocess), `AnthropicProvider` (official SDK, model configurable), `OpenAICompatProvider` (base_url + key), `FakeProvider` (replays recorded fixtures by prompt hash). Preflight checks register with doctor. Provider string format `ollama:qwen3:14b`, `anthropic:<model-id>`, `openai_compat:<base_url>#<model>`.
- **AC:** each provider unit-tested with respx; Ollama integration test with a tiny model
- **Depends on:** S0-T09

### S1-T06: Script writer
- **Labels:** type: feature, area: script, priority: p0, size: L, sprint: 1
- **Description:** Build system prompt from profile (`writing` and `speech` sections) and a fixed rule block: output Script Markdown only, chunk numbering, allowed markers only, keep `{verbatim}` blocks exact, keep signature exact, no emoji, no markdown other than chunk headers, explain big words inline, spoken transitions for list items, add `interactive_moments` count of participatory lines, target length `target_minutes * 130 * rate` words. User prompt carries block JSON. Store prompt template in `audio_smith/script/prompts/writer.md` with a version number included in the script cache key.
- **AC:** FR-005 ACs; with FakeProvider the reference letter yields the golden script
- **Depends on:** S1-T03, S1-T04, S1-T05

### S1-T07: Script Markdown parser, serializer, validator
- **Labels:** type: feature, area: script, priority: p0, size: M, sprint: 1
- **Description:** Parse frontmatter and chunks, round-trip serialize, validate per FR-006, corrective retry loop in writer.
- **AC:** FR-006 ACs; round-trip property test
- **Depends on:** S1-T06

### S1-T08: Lexicon
- **Labels:** type: feature, area: script, priority: p2, size: S, sprint: 1
- **Description:** Merge profile lexicon with project `lexicon.yaml`; apply at synthesis time only.
- **AC:** FR-007 ACs
- **Depends on:** S1-T04

### S1-T09: `script` command
- **Labels:** type: feature, area: cli, priority: p0, size: S, sprint: 1
- **Description:** Wire stages 1 and 2 with cache for blocks and scripts; `--force` bypasses cache; writes `{slug}.blocks.json` and `{slug}.en.script.md`. Slug from URL path stem, sanitized.
- **AC:** second run on unchanged page is a cache hit under 2 s
- **Depends on:** S1-T07

### Sprint 1 Gate (hard stop)
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
- **Description:** `Capabilities`, `SynthParams` (rate, seed, lang, temperature), `PcmAudio` (numpy float32 + sample_rate), backend registry by id, `MockBackend` producing deterministic tones whose duration is proportional to text length and pitch derived from voice id.
- **AC:** FR-009 ACs; mock is deterministic across platforms
- **Depends on:** S0-T05

### S2-T02: OpenAI-compatible backend
- **Labels:** type: feature, area: tts, priority: p0, size: M, sprint: 2
- **Description:** One class using the official `openai` SDK `audio.speech.create` with `response_format="wav"`, configurable `base_url`, `model`, `api_key`. Adapter hooks: `map_voice(VoiceRef)`, `map_params(SynthParams)`, `map_text(str)` for markers. Used directly as `openai` (cloud) and `openai_compat`.
- **AC:** respx-mocked tests for success, 4xx, 5xx with retry, timeout
- **Depends on:** S2-T01

### S2-T03: Maya 2 Native backend
- **Labels:** type: feature, area: tts, priority: p0, size: L, sprint: 2
- **Description:** Adapter over S2-T02 pointed at the local Maya 2 server (`AUDIO_SMITH_MAYA2_URL`, default `http://127.0.0.1:8080/v1`, verified upstream default port). Built-in voice ids pass through. Cloned voices: register the consented `reference.24k.wav` once with `POST /v1/voices` `{voice_id, ref_audio_b64, ref_text, lang, mode, replace}` using voice id `as-{voice_id}-{clip_hash[:8]}` (idempotent), then pass that id as `voice` to `POST /v1/audio/speech`. The server requires `speed: 1.0`, so the profile speaking rate is applied after synthesis with ffmpeg `atempo` (ADR-016). The Python package and class are `maya3` / `Maya3TTS`; `maya3` is not on PyPI (install from git). Optional `--maya2-mode inproc` loads the model in-process via the Python package when the `maya2` extra is installed. Capabilities: 12 languages (en plus as, bn, gu, hi, kn, ml, mr, or, pa, ta, te), cloning true, 24 kHz, license Apache-2.0, commercial_ok true. Pause markers become separate requests joined by silence (Maya 2 has no inline tags); `*emphasis*` stripped.
- **AC:** FR-010 ACs; `it_maya2_synth_clone_returns_24khz_mono` passes on the GPU runner; doctor reports server reachability and loaded model
- **Depends on:** S2-T02, S2-T05

### S2-T04: Kokoro backend (CPU fallback)
- **Labels:** type: feature, area: tts, priority: p1, size: M, sprint: 2
- **Description:** In-process Kokoro (`kokoro` package, 82M weights, Apache-2.0); English voices; clone false. Downloads weights on first use to `models/` with checksum verification.
- **AC:** integration test on CPU in CI; capability flags correct
- **Depends on:** S2-T01

### S2-T05: Voice registry, consent, clip check
- **Labels:** type: feature, area: voices, priority: p0, size: L, sprint: 2
- **Description:** `voice add|list|check|remove` commands; voice directory layout per ARCHITECTURE; consent record required (interactive prompt or flags); clip check per FR-011 using soundfile + numpy (duration, rate, clipping, SNR estimate via noise floor percentile); clip normalized and resampled to 24 kHz mono copy stored as `reference.24k.wav`; voice clip hash computed. Consent enforcement lives in `voices.registry.resolve()` so every front door inherits it.
- **AC:** FR-011 ACs; `test_consent_clone_unregistered_voice_raises`; clip check fixtures pass and fail as expected
- **Depends on:** S0-T10

### S2-T06: Backend preflight and doctor integration
- **Labels:** type: feature, area: cli, priority: p1, size: S, sprint: 2
- **Description:** Register per-backend checks (server reachable, model loaded, GPU visible via `torch.cuda.is_available()` when torch installed, weights present), registered voices valid.
- **AC:** doctor table shows each backend with status and hint
- **Depends on:** S2-T03, S2-T04

### S2-T07: License guard
- **Labels:** type: feature, area: tts, priority: p2, size: S, sprint: 2
- **Description:** If a backend reports `commercial_ok: false`, require `--accept-noncommercial` and record it in the manifest warnings.
- **AC:** unit tests for both paths
- **Depends on:** S2-T01

### Sprint 2 Gate (hard stop)
- [ ] `mr-audio-smith render tests/fixtures/scripts/valid.script.md --backend mock` produces WAV chunks
- [ ] Maya 2 renders a chunk in a registered cloned voice on the GPU runner
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
- **Description:** Convert script chunks into synthesis units: split on `[pause N]` markers into segments, enforce backend `max_chars` by sentence-splitting (never mid-sentence), apply lexicon, compute chunk keys.
- **AC:** unit tests for split rules, lexicon application, key stability
- **Depends on:** S2-T01, S1-T08

### S3-T02: Synthesis runner with cache and resume
- **Labels:** type: feature, area: tts, priority: p0, size: L, sprint: 3
- **Description:** Iterate units, cache hits skip, misses synthesize with retries (2, exponential backoff with jitter), write WAV to cache atomically (temp file + rename), progress bar (rich), Ctrl-C safe, `--chunks` subset rendering.
- **AC:** FR-012 ACs; killing mid-run and re-running only renders the remainder
- **Depends on:** S3-T01

### S3-T03: Speaker similarity QA
- **Labels:** type: feature, area: qa, priority: p1, size: L, sprint: 3
- **Description:** `qa` extra using `resemblyzer` (or SpeechBrain ECAPA if lighter on the target platform; record the choice as an ADR). Embed reference clip once; per chunk compute cosine similarity; if under threshold, re-render with new seed up to `takes_per_chunk` (default 2); keep best; record scores. Skipped gracefully when extra not installed (warning in manifest).
- **AC:** FR-013 ACs; unit tests with stubbed embeddings
- **Depends on:** S3-T02

### S3-T04: Assembler
- **Labels:** type: feature, area: master, priority: p0, size: M, sprint: 3
- **Description:** Concatenate segments with silences (pause markers, `pause_after_heading_ms`, `pause_between_chunks_ms`), short crossfade (10 ms) at joins to avoid clicks, resample to 44.1 kHz, track chunk start and end timestamps for VTT.
- **AC:** golden test on mock audio: total duration equals sum of parts plus pauses within 5 ms
- **Depends on:** S3-T02

### S3-T05: ffmpeg mastering chain
- **Labels:** type: feature, area: master, priority: p0, size: L, sprint: 3
- **Description:** `ffmpeg.py` wrapper using argument arrays. Chain: high-pass 70 Hz, gentle de-esser, light compression, optional intro and outro stings, optional music bed with `sidechaincompress` ducking (bed at -24 dB under voice), two-pass `loudnorm` to I=-16, TP=-1.5, LRA=11, encode MP3 (libmp3lame 128k mono) and optional Opus. Ship two original CC0 stings in `assets/stings/` (generated procedurally in a script, documented in THIRD_PARTY_LICENSES as original).
- **AC:** FR-014 ACs; `test_master_loudness_within_target` measures output with ffmpeg ebur128
- **Depends on:** S3-T04

### S3-T06: ID3 tagging and cover art
- **Labels:** type: feature, area: master, priority: p2, size: S, sprint: 3
- **Description:** mutagen tags: TIT2 title, TPE1 author (from page meta author or config), TALB site name, TDRC date, APIC cover from page `og:image` when same-origin and under 1 MB, else none.
- **AC:** tags readable by mutagen in tests
- **Depends on:** S3-T05

### S3-T07: WebVTT captions
- **Labels:** type: feature, area: publish, priority: p1, size: M, sprint: 3
- **Description:** Sentence-level cues from chunk timestamps; distribute within a chunk by character-length proportion, then refine with optional forced alignment (deferred; record as enhancement).
- **AC:** FR-015 ACs on mock audio
- **Depends on:** S3-T04

### S3-T08: Manifest and schemas
- **Labels:** type: feature, area: publish, priority: p0, size: M, sprint: 3
- **Description:** Build and write manifest per ARCHITECTURE; publish `schemas/manifest.schema.json`, `schemas/blocks.schema.json`, `schemas/profile.schema.json`; validate in tests.
- **AC:** FR-016 ACs
- **Depends on:** S3-T05, S3-T07

### S3-T09: `run` and `render` commands end to end
- **Labels:** type: feature, area: cli, priority: p0, size: L, sprint: 3
- **Description:** Wire all stages; `--approve` pauses after script generation, opens the script in `$EDITOR`, then continues; `--dry-run` prints plan and cache status; output layout `out/{slug}/` with all artifacts. Parent track rendered when blocks exist with `track: parent`.
- **AC:** smoke test with mocks passes; real run on reference letter produces a listenable MP3 in a cloned voice on the GPU runner; FR-026 ACs
- **Depends on:** S3-T03, S3-T06, S3-T08

### S3-T10: Python API
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 3
- **Description:** `audio_smith.narrate(source, profile=..., voice=..., backend=..., langs=..., out=...) -> Manifest` and stage functions (`extract`, `write_script`, `render_script`, `master`, `publish`). CLI becomes a thin layer over the API.
- **AC:** documented in README; API used by CLI tests
- **Depends on:** S3-T09

### S3-T11: Performance pass
- **Labels:** type: perf, area: tts, priority: p2, size: M, sprint: 3
- **Description:** Measure NFR-003 on the reference letter; enable request concurrency for HTTP backends (bounded semaphore, default 2) since Maya 2 serves concurrent streams; record numbers in `docs/PERFORMANCE.md`.
- **AC:** NFR-003 met or a tracked issue explains the gap
- **Depends on:** S3-T09

### Sprint 3 Gate (hard stop)
- [ ] Reference letter narrated end to end in a cloned voice, kid-5 profile
- [ ] Loudness, true peak, VTT alignment verified by automated tests
- [ ] Unchanged re-run under 2 seconds
- [ ] Internal listening test (TEST_PLAN protocol) averages 4 or higher
- [ ] Coverage at or above targets for `tts`, `master`, `publish`, `qa`
- [ ] Retrospective written, `sprint-3-complete` tagged

---

## Sprint 4: Publish and Site

**Milestone:** Sprint 4: Publish and Site
**Duration:** 1 week
**Goal:** Narrations appear on real pages through a polished player, extra languages work, a whole site can be narrated in one command, and a GitHub Action does it on push.

### S4-T01: `<audio-smith-player>` web component
- **Labels:** type: feature, area: player, priority: p0, size: L, sprint: 4
- **Description:** TypeScript, no dependencies, built with `bun build` to ESM and IIFE, published as `@mr-audio-smith/player`. Attributes: `src`, `captions`, `label`, `size` (`default` or `kid`), `tracks` (JSON array of `{lang, label, src, captions}`), `theme` (`auto`, `light`, `dark`). Wraps a slotted native `<audio>` so the page works without JS. Implements DESIGN.md states, keyboard (Space, K play or pause; arrows seek 5 s; C captions; L language), Media Session API metadata, remembers last position per src in localStorage inside try/catch.
- **AC:** NFR-007 and NFR-011; e2e tests for keyboard, captions, language toggle, no-JS fallback
- **Depends on:** S0-T06

### S4-T02: Embed snippet generator
- **Labels:** type: feature, area: publish, priority: p0, size: S, sprint: 4
- **Description:** Generate `{slug}.embed.html` per FR-017. Player script reference is configurable: self-hosted path (default `/media/audio/audio-smith-player.js`, copied into the output dir) or jsDelivr URL pinned to the exact version.
- **AC:** snippet validates as HTML; renders correctly with and without JS
- **Depends on:** S4-T01, S3-T08

### S4-T03: Inject command
- **Labels:** type: feature, area: publish, priority: p0, size: M, sprint: 4
- **Description:** FR-018 using a parser that preserves original formatting outside markers (string splice on marker offsets, never re-serialize the whole DOM). `--selector` (default `h1`) decides where markers go if absent.
- **AC:** idempotence and untouched-outside tests; dry-run diff output
- **Depends on:** S4-T02

### S4-T04: Translation and language tracks
- **Labels:** type: feature, area: script, priority: p1, size: M, sprint: 4
- **Description:** FR-008. Translate validated script per extra language, validate alignment, render each language with the same voice (cross-lingual cloning on Maya 2), manifest lists tracks, embed gets language toggle. Backends lacking a language fail preflight with a clear message.
- **AC:** Hindi track rendered on GPU runner; alignment test passes
- **Depends on:** S3-T09

### S4-T05: Site batch mode
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 4
- **Description:** FR-019. Parse index page links, filter same-origin plus glob, run sequentially with shared backend session, summary table (page, status cached or rendered or failed, duration). `--inject-root <dir>` maps URLs to local HTML files for injection in a static-site repo.
- **AC:** fixture index with 3 pages: second run renders 0
- **Depends on:** S4-T03

### S4-T06: GitHub Action
- **Labels:** type: feature, area: action, priority: p1, size: L, sprint: 4
- **Description:** `action/action.yml` composite action. Inputs: `pages-glob`, `site-url`, `profile`, `voice`, `backend`, `server-url` (use remote `mr-audio-smith serve` instead of local GPU), `server-token`, `commit` (bool), `output-dir`. Steps: detect changed files via `git diff` on the push range, map to URLs, run `site` or remote jobs, inject, commit with message `chore(audio): narrate {n} pages [skip ci]`. Voice clips are never stored in the site repo; with a remote server the voice lives on the server.
- **AC:** FR-025 ACs; example workflow in `examples/static-site/.github/workflows/narrate.yml`; tested in a throwaway repo via `act` or a test repo
- **Depends on:** S4-T05

### S4-T07: Example for the reference site
- **Labels:** type: docs, area: publish, priority: p2, size: S, sprint: 4
- **Description:** `examples/letters-to-a-child/` with `audio-smith.toml`, `profiles/kid-5.yaml` override, lexicon, data-narrate markup guide for letter templates, and the workflow file.
- **AC:** example runs end to end with mock backend in CI
- **Depends on:** S4-T06

### Sprint 4 Gate (hard stop)
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
- **Description:** FastAPI app mounted by `mr-audio-smith studio`: list projects in `out/`, get and save script (with validation), render chunk (returns take id), list takes with similarity scores, select take, re-master, approve (writes `approved: true` to manifest). Binds 127.0.0.1; random per-session token in URL to prevent other local sites from calling it (CSRF guard).
- **AC:** route tests with httpx TestClient; token enforced
- **Depends on:** S3-T10

### S5-T02: Studio frontend shell
- **Labels:** type: feature, area: studio, priority: p0, size: M, sprint: 5
- **Description:** `web/studio` with Vite + TypeScript + Preact, design tokens from Design System, layout from DESIGN.md wireframes, built assets copied into `audio_smith/studio/static/` at package build.
- **AC:** no external network requests (verified in e2e via request interception)
- **Depends on:** S5-T01

### S5-T03: Script editor with chunk list
- **Labels:** type: feature, area: studio, priority: p0, size: L, sprint: 5
- **Description:** Chunk list with status (cached, stale, rendering, failed), inline editor per chunk with marker autocomplete for `[pause N]`, live validation errors, save marks edited chunks stale.
- **AC:** e2e for edit, validate, save
- **Depends on:** S5-T02

### S5-T04: Take comparison
- **Labels:** type: feature, area: studio, priority: p1, size: M, sprint: 5
- **Description:** Render another take with new seed, play takes A and B, show similarity score and duration, keep best.
- **AC:** `e2e_US017_studio_compare_takes_keep_best`
- **Depends on:** S5-T03

### S5-T05: Full preview and approve
- **Labels:** type: feature, area: studio, priority: p1, size: S, sprint: 5
- **Description:** Re-master and play the full track in the real `<audio-smith-player>`, approve button, optional inject from UI with diff preview.
- **AC:** approve persists; inject diff shown before write
- **Depends on:** S5-T04, S4-T03

### Sprint 5 Gate (hard stop)
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
- **Description:** Walk the Security Guidelines checklist; add `pip-audit`, `bandit` (via ruff S rules), `npm audit`, `gitleaks` to CI; fuzz the extractor with hypothesis-generated HTML; verify SSRF guard against DNS rebinding (resolve once, connect to resolved IP).
- **AC:** zero high or critical findings; report in `docs/SECURITY_REVIEW.md`
- **Depends on:** S5 complete

### S6-T02: Documentation site content
- **Labels:** type: docs, area: cli, priority: p0, size: L, sprint: 6
- **Description:** README (template below), `docs/guide/` (quickstart, voices and consent, profiles, backends, site mode, GitHub Action, Studio, troubleshooting), `docs/reference/` (CLI generated via typer docs, Python API via mkdocstrings), mkdocs-material site deployed to GitHub Pages at getaudiosmith.com.
- **AC:** every CLI command and flag documented; quickstart runs in under 10 minutes on a fresh machine
- **Depends on:** S6-T01

### S6-T03: THIRD_PARTY_LICENSES.md
- **Labels:** type: docs, area: packaging, priority: p0, size: S, sprint: 6
- **Description:** Generate with `pip-licenses` and `license-checker` for npm; add model weights section (Maya 2 Native: Apache-2.0; Kokoro-82M: Apache-2.0; Chatterbox: MIT; resemblyzer: Apache-2.0) and assets. Verify every entry at implementation time.
- **AC:** CI job fails if a new dependency lacks an entry
- **Depends on:** S6-T01

### S6-T04: Listening test round
- **Labels:** type: test, area: qa, priority: p0, size: S, sprint: 6
- **Description:** Run the TEST_PLAN listening protocol on 3 letters (en) and 1 letter (hi). Record scores in `docs/LISTENING_TESTS.md`.
- **AC:** all averages 4 or higher
- **Depends on:** S6-T02

### S6-T05: Release pipeline
- **Labels:** type: chore, area: packaging, priority: p0, size: M, sprint: 6
- **Description:** `.github/workflows/release.yml` per the Versioning section: on tag `v*.*.*`, verify versions, build sdist and wheel with `uv build`, publish to PyPI via trusted publishing (OIDC, no tokens), build and publish npm packages with provenance, create GitHub Release with changelog body, attach SBOM (CycloneDX) and artifacts.
- **AC:** dry run to TestPyPI succeeds from a `v1.0.0-rc.1` tag
- **Depends on:** S6-T03

### S6-T06: Ship v1.0.0
- **Labels:** type: chore, area: packaging, priority: p0, size: S, sprint: 6
- **Description:** Follow the release checklist exactly; then narrate every letter on the reference site with the published version as the launch validation.
- **AC:** `uv tool install mr-audio-smith` installs v1.0.0; reference site letters have players
- **Depends on:** S6-T04, S6-T05

### Sprint 6 Gate (hard stop)
- [ ] Release checklist complete
- [ ] v1.0.0 on PyPI and npm with provenance
- [ ] Docs site live
- [ ] Reference site narrated with v1.0.0
- [ ] Retrospective written, `sprint-6-complete` tagged, `v1.0.0` annotated tag on `main`

---
## Versioning, Changelog, and Release

### Semantic versioning

`MAJOR.MINOR.PATCH`, following semver 2.0.0.

- **MAJOR:** breaking change to the CLI flags or exit codes, the Python API, the REST or MCP contracts, the Script Markdown format, the profile schema, the manifest schema, or the player attributes.
- **MINOR:** new backward-compatible capability (new backend, new profile field with a default, new command, new MCP tool).
- **PATCH:** bug fixes, performance, docs, dependency bumps with no behavior change.
- Pre-releases: `1.1.0-rc.1`. Before 1.0.0, minor bumps may break, and the changelog must say so.
- File format schemas carry their own version (`audio-smith/script@1`). A schema bump is always at least a MINOR, and a breaking schema change is a MAJOR.

### Version source of truth

`pyproject.toml` `[project].version` is the only place a human edits the version. Everything else derives from it or is checked against it:

| File | How it stays in sync |
|---|---|
| `audio_smith/__init__.py` | reads `importlib.metadata.version("mr-audio-smith")` at runtime (no literal) |
| `player/package.json` | set by `bump-version.sh`, checked by `check-versions.sh` |
| `integrations/pi/package.json` | set by `bump-version.sh`, checked |
| `web/studio/package.json` | set by `bump-version.sh`, checked |
| `charts/mr-audio-smith/Chart.yaml` (`version`, `appVersion`) | set by `bump-version.sh`, checked |
| `action/action.yml` (default image tag) | set by `bump-version.sh`, checked |

### `scripts/check-versions.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

CANONICAL=$(python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
PY
)

check() {
  local actual=$1 file=$2
  if [[ "$actual" != "$CANONICAL" ]]; then
    echo "✗ Version mismatch in $file: expected $CANONICAL, got $actual"
    exit 1
  fi
  echo "✓ $file: $CANONICAL"
}

check "$(jq -r '.version' player/package.json)" "player/package.json"
check "$(jq -r '.version' integrations/pi/package.json)" "integrations/pi/package.json"
check "$(jq -r '.version' web/studio/package.json)" "web/studio/package.json"
check "$(yq -r '.version' charts/mr-audio-smith/Chart.yaml)" "charts/mr-audio-smith/Chart.yaml (version)"
check "$(yq -r '.appVersion' charts/mr-audio-smith/Chart.yaml)" "charts/mr-audio-smith/Chart.yaml (appVersion)"
check "$(yq -r '.inputs.image-tag.default' action/action.yml)" "action/action.yml (image-tag)"

echo "── All versions consistent: $CANONICAL ──"
```

Runs in CI on every PR to `staging` and `main` (job `check-versions`).

### `scripts/bump-version.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
NEW="${1:?Usage: $0 <new-version>}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?$ ]] || { echo "Invalid semver: $NEW"; exit 2; }
cd "$(git rev-parse --show-toplevel)"
uv version "$NEW"   # updates pyproject.toml (verify flag name for the installed uv version)
for f in player/package.json integrations/pi/package.json web/studio/package.json; do
  tmp=$(mktemp); jq --arg v "$NEW" '.version=$v' "$f" > "$tmp" && mv "$tmp" "$f"
done
yq -i ".version = \"$NEW\" | .appVersion = \"$NEW\"" charts/mr-audio-smith/Chart.yaml
yq -i ".inputs.image-tag.default = \"$NEW\"" action/action.yml
./scripts/check-versions.sh
```

### Version bump process

1. On a `chore/release-x.y.z` branch off `develop`, run `scripts/bump-version.sh x.y.z`.
2. Move `[Unreleased]` entries in `CHANGELOG.md` under `## [x.y.z] - YYYY-MM-DD`; leave an empty `[Unreleased]` with all subsections.
3. Commit `chore(release): x.y.z`, PR to `develop`, then `develop` -> `staging` -> `main` per release checklist.
4. Tag `main` with an annotated tag `vx.y.z` (CI release workflow triggers on the tag).

### Changelog protocol

Keep a Changelog 1.1.0 format. `[Unreleased]` is always present at the top with subsections `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Every user-facing PR adds a line under `[Unreleased]` in the same PR. Lines are written for users ("Added `--lang` flag to render extra language tracks"), not for developers ("refactor translate.py"). Link compare URLs at the bottom.

### `scripts/extract-changelog.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
VERSION="${1:?Usage: $0 <version>}"
awk "/^## \\[${VERSION}\\]/{found=1; next} found && /^## \\[/{exit} found{print}" CHANGELOG.md
```

### Git tagging strategy

- **Releases:** annotated tags on `main`: `git tag -a v1.0.0 -m "mr-audio-smith 1.0.0"`.
- **Sprints:** lightweight tags on `staging`: `sprint-{n}-complete`.
- **Release candidates:** annotated tags on `staging`: `v1.1.0-rc.1` (publishes to TestPyPI and npm `next` dist-tag only).
- Tags are never moved or deleted after push.

### Release workflow (CI)

```
push tag v*.*.*
   |
   +-> verify: tag == pyproject version (check-versions.sh), tag is on main (or staging for rc)
   +-> full CI (lint, typecheck, unit, integration, e2e, smoke)
   +-> build:
   |     uv build -> sdist + wheel
   |     bun build -> @mr-audio-smith/player, @mr-audio-smith/pi-extension
   |     docker buildx (linux/amd64, linux/arm64): cpu and cuda variants
   +-> sign + attest: cosign keyless (OIDC) for images, npm --provenance, PyPI attestations
   +-> SBOM: CycloneDX for Python and npm, attached to release
   +-> publish:
   |     PyPI (trusted publishing)   | TestPyPI for -rc
   |     npm (latest)                | npm next for -rc
   |     ghcr.io/serverless-ventures/mr-audio-smith:{version, version-cuda, latest}
   |     Helm chart to ghcr.io OCI registry
   +-> GitHub Release: body from extract-changelog.sh, artifacts, SBOMs
   +-> docs: mkdocs gh-deploy for the version
```

### Release checklist

**Pre-release**
- [ ] All milestone issues closed
- [ ] `CHANGELOG.md` complete for this version
- [ ] `check-versions.sh` passes after bump
- [ ] THIRD_PARTY_LICENSES.md current
- [ ] Security review items closed
- [ ] Listening tests at or above 4 recorded

**Staging validation**
- [ ] `develop` merged to `staging`, CI green including `gpu-integration`
- [ ] Install from TestPyPI rc in a clean venv; run quickstart
- [ ] Narrate the 3 fixture letters plus 1 live page with Maya 2 and with Kokoro
- [ ] Player verified in Safari, Chrome, Firefox, iOS Safari, Android Chrome
- [ ] Docker CPU and CUDA images run `doctor` green

**Release**
- [ ] PR `staging` -> `main` approved and merged
- [ ] Annotated tag pushed
- [ ] Release workflow green; packages visible on PyPI, npm, GHCR
- [ ] GitHub Release body correct

### Post-release actions

1. Back-merge `main` into `develop`.
2. Announce: SnackOnAI newsletter deep-dive and LinkedIn post (use the SnackOnAI composer and LinkedIn skills).
3. Close the milestone; open next milestone.
4. Watch issues for 72 hours; any P0 bug gets a hotfix branch from `main`.
5. Update the reference site to the released player version.

---

## Coding Standards

### Python (core, server, MCP)

- Python 3.12+ syntax; `from __future__ import annotations` not needed.
- `mypy --strict` clean. No `Any` except at third-party boundaries, wrapped immediately in typed models. No `# type: ignore` without an error code and a comment.
- pydantic v2 models for every data format, config, and API payload. No untyped dicts crossing module boundaries.
- Errors: raise typed `AudioSmithError` subclasses with `code`, `stage`, `hint`. Never `except Exception:` without re-raising or converting. Never `sys.exit` outside `cli.py`.
- No `print()` outside `cli.py` and Rich console helpers; use `structlog` for logs.
- Subprocess: `subprocess.run([...], check=True, capture_output=True, timeout=...)` with argument lists. `shell=True` is forbidden.
- Paths: `pathlib.Path` only. File names derived from URLs go through `safe_slug()`; writes go through `atomic_write()`.
- I/O boundaries are injectable (fetcher, LLM provider, TTS backend, clock, filesystem root) so unit tests never touch the network or GPU.
- Functions under 50 lines; modules under 400 lines; split before exceeding.
- Docstrings on every public function (Google style); explain why, not what.
- No global mutable state; settings passed explicitly or via a context object.
- Async only in server and MCP layers; core pipeline is sync with an executor bridge.

### TypeScript (player, Studio, Pi extension)

- `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`.
- No `any`; use `unknown` and narrow. No non-null assertions without a comment.
- No `console.log` in shipped code; a `debug` flag gates diagnostic logging.
- Player: zero runtime dependencies, Shadow DOM, CSS custom properties for theming, every user-visible string overridable by attribute.
- ESLint with `@typescript-eslint/strict-type-checked`; Prettier formatting.
- Tests with vitest; e2e with Playwright.

### General

- No magic numbers: name constants (`DEFAULT_TARGET_LUFS = -16.0`).
- TODO format: `TODO(#123): explanation`; a TODO without an issue fails lint.
- Conventional Commits:
  ```
  feat:     new feature
  fix:      bug fix
  chore:    maintenance, tooling, dependencies
  docs:     documentation only
  test:     testing infrastructure or coverage
  refactor: code improvement, no behavior change
  perf:     performance improvement
  ci:       GitHub Actions and pipelines
  ```
- No em dashes anywhere in prose, comments, docs, or copy (enforced by pre-commit). No "game-changer" or "revolutionary" in any copy.
- Every commit compiles and passes unit tests (bisectable history).

---

## Security Guidelines

### Input handling
- Fetch: scheme allowlist, SSRF guard (block 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fc00::/7, fe80::/10, and cloud metadata addresses), resolve once and pin the IP for the connection, max size, max redirects, timeout.
- HTML is parsed, never rendered or executed. No JavaScript engine in the pipeline.
- Extracted text is treated as untrusted data in LLM prompts: wrapped in delimiters with an instruction that the content is material to narrate, not instructions to follow. The validator catches any output that deviates from Script Markdown, which limits prompt-injection impact to wording within chunks.
- Path traversal: every output path is resolved and verified to be inside the output root.

### Voice cloning safety
- Consent record required for every cloned voice, enforced in core.
- Reference clips stored with `0600` permissions; never uploaded anywhere except the configured local or self-hosted TTS server.
- Manifests record the voice id, never the clip or consent statement.
- README and docs state plainly: only clone your own voice or a voice you have written permission to use.

### Server and Studio
- Default bind `127.0.0.1`. Binding to any other address requires `AUDIO_SMITH_SERVER_TOKEN`; requests without the bearer token get 401.
- Studio uses a per-session random token and rejects requests without it; sets `Content-Security-Policy: default-src 'self'; media-src 'self' blob:; connect-src 'self'`.
- CORS disabled by default on the server; explicit allowlist when enabled.
- Job artifacts served only through the API with path validation.
- Rate limit job creation per token (default 30 per hour).

### Dependency security
- `uv.lock`, `bun.lockb` committed; CI installs with `--frozen`.
- `pip-audit`, `npm audit --audit-level=high`, `gitleaks`, and Dependabot.
- Model weights downloaded over HTTPS with pinned revisions and SHA-256 verification.
- Docker images: non-root user, read-only root filesystem, no shell in the runtime CPU image (distroless where feasible), cosign-signed.

### Privacy
- Zero telemetry. No analytics in player or Studio.
- Local-first default: Ollama and local TTS. Cloud providers only when explicitly configured; `doctor` prints a "cloud providers active" warning when any are.
- Player stores only playback position in localStorage, inside try/catch.

### Secrets
- API keys only from environment variables or the OS keyring (`keyring` package); never in `audio-smith.toml`, manifests, logs, or error messages. Logs redact any value whose key matches `*key*`, `*token*`, `*secret*`.

---

## Design System

### Principles
Warm, calm, and legible. The player sits on someone else's page, often a family page read by a child, so it must feel friendly and never compete with the content.

### Color tokens

```css
:root {
  /* Surfaces */
  --as-bg:            #FFFFFF;
  --as-surface:       #F6F8F5;   /* player card */
  --as-surface-2:     #ECF1EA;   /* hover, track */
  --as-border:        #D7E0D3;

  /* Text */
  --as-text:          #1E2A22;
  --as-text-muted:    #5B6B60;
  --as-text-inverse:  #FFFFFF;

  /* Accent (sage, pairs with the reference site's #7daa8b theme color) */
  --as-accent:        #4E8A62;   /* play button, progress; 4.6:1 on white */
  --as-accent-hover:  #3F7552;
  --as-accent-soft:   #DCEBDF;

  /* Kid accents (kid variant only) */
  --as-sun:           #F4B740;
  --as-sky:           #5AA9E6;

  /* Feedback */
  --as-error:         #B3261E;
  --as-focus:         #1F6FEB;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --as-bg: #101512; --as-surface: #18201B; --as-surface-2: #222C25; --as-border: #2E3A32;
    --as-text: #E8EFE9; --as-text-muted: #A3B2A7; --as-accent: #7DBF92; --as-accent-hover: #93CEA6;
    --as-accent-soft: #23362A;
  }
}
:root[data-theme="dark"] { /* same values as the dark block above */ }
```

Studio uses the same tokens plus `--as-stale: #C77D12` (chunk needs re-render) and `--as-ok: #2E7D4F`.

### Typography
- Player inherits the host page font by default (`font: inherit`) so it feels native; fallback stack `ui-rounded, "SF Pro Rounded", "Nunito", system-ui, sans-serif`.
- Studio: `Inter` for UI, `JetBrains Mono` for script text (chunk numbers and pause markers read clearly in mono).
- Scale (px): 12, 14, 16, 18, 22, 28. Player label 16 (kid variant 22). Time display uses tabular numerals.
- Weights: 400 body, 600 labels and buttons. No weights above 700.

### Spacing
4px base unit: 4, 8, 12, 16, 24, 32, 48. Player padding 12 (kid 20). Radius: 12 card, full circle for play button.

### Signature element
**The breathing waveform.** A row of 28 slim rounded bars beneath the label, drawn from real peak data in the manifest (precomputed during mastering, embedded as a compact attribute). While playing, bars to the left of the playhead fill with `--as-accent` and the bar at the playhead gently "breathes" (scale 1.0 to 1.15, 1.6 s ease-in-out loop). It echoes the "find your calm, take three slow breaths" spirit of the flagship letters. Disabled under `prefers-reduced-motion`.

### Components
Player: PlayButton, Label, Waveform, Time, CaptionsToggle, LanguageToggle, CaptionLine (overlay below card), ErrorState.
Studio: ProjectList, ChunkList, ChunkRow (status pill), ChunkEditor, MarkerChip, TakeCompare, RenderQueue, MasterPreview, ApprovePanel, DiffViewer, Toast.

### Anti-patterns (must not appear)
- Autoplay of any kind
- Gradients, glassmorphism, drop shadows heavier than `0 1px 2px rgba(0,0,0,.06)`
- Emoji inside the player UI
- Volume sliders on mobile (use device volume)
- Tiny touch targets under 44px (under 64px for the kid play button)
- Download buttons by default (opt-in attribute only)
- Brand watermarks or "powered by" badges in the player
- Spinners longer than 300 ms without a text status
- Color as the only signal for chunk status in Studio (always pair with a text pill)

---

## Environment Model

Three environments.

- **dev:** developer laptop; mock or Kokoro backend; Ollama small model; everything on localhost.
- **stage:** GPU runner or LAN GPU box running the Maya 2 server and `mr-audio-smith serve`; TestPyPI rc builds; a staging copy of the reference site.
- **prod:** released packages; user machines; optional shared server for site automation.

| Variable | dev | stage | prod | Notes |
|---|---|---|---|---|
| `AUDIO_SMITH_ENV` | `dev` | `stage` | `prod` | Affects defaults and log level |
| `AUDIO_SMITH_LOG_LEVEL` | `debug` | `info` | `info` | |
| `AUDIO_SMITH_LOG_FORMAT` | `pretty` | `json` | `pretty` (CLI) / `json` (server) | |
| `AUDIO_SMITH_CACHE_DIR` | `./.audio-smith/cache` | `/var/lib/audio-smith/cache` | `~/.cache/audio-smith` | |
| `AUDIO_SMITH_OUT_DIR` | `./out` | `/var/lib/audio-smith/out` | `./audio` | |
| `AUDIO_SMITH_VOICES_DIR` | `./voices` | `/var/lib/audio-smith/voices` | `~/.config/audio-smith/voices` | 0700 dir |
| `AUDIO_SMITH_DEFAULT_BACKEND` | `mock` | `maya2` | `maya2` | |
| `AUDIO_SMITH_MAYA2_URL` | `http://127.0.0.1:8080/v1` | `http://maya2:8080/v1` | `http://127.0.0.1:8080/v1` | Maya 2 server default port is 8080 (verified) |
| `AUDIO_SMITH_LLM` | `ollama:qwen3:0.6b` | `ollama:qwen3:14b` | `ollama:qwen3:14b` | Any provider string |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | `http://ollama:11434` | `http://127.0.0.1:11434` | |
| `ANTHROPIC_API_KEY` | unset | optional | optional | Only if anthropic provider used |
| `OPENAI_API_KEY` | unset | optional | optional | Only if openai backend/provider used |
| `AUDIO_SMITH_SERVER_HOST` | `127.0.0.1` | `0.0.0.0` | `127.0.0.1` | Non-localhost needs token |
| `AUDIO_SMITH_SERVER_PORT` | `7340` | `7340` | `7340` | |
| `AUDIO_SMITH_SERVER_TOKEN` | unset | set (secret) | set if exposed | |
| `AUDIO_SMITH_STUDIO_PORT` | `7341` | `7341` | `7341` | Always 127.0.0.1 |
| `AUDIO_SMITH_QA_THRESHOLD` | `0.75` | `0.75` | `0.75` | |
| `AUDIO_SMITH_MAX_FETCH_BYTES` | `5242880` | `5242880` | `5242880` | |
| `AUDIO_SMITH_ALLOW_PRIVATE` | `true` | `false` | `false` | SSRF guard bypass |

Provide `.env.dev.example`, `.env.stage.example`, `.env.prod.example`.

---

## Dependency Versions

Verify latest stable versions at implementation time and pin in lock files. Constraints below are minimums.

### Python (core)

```toml
[project]
requires-python = ">=3.12,<3.14"
dependencies = [
  "typer>=0.12",
  "rich>=13.7",
  "httpx>=0.27",
  "selectolax>=1.0",        # lexbor backend; the modest backend was removed in 1.0
  "trafilatura>=1.12",
  "emoji>=2.12",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "pyyaml>=6.0",
  "structlog>=24.1",
  "numpy>=1.26",
  "soundfile>=0.12",
  "pydub>=0.25",
  "mutagen>=1.47",
  "openai>=1.40",          # OpenAI-compatible TTS client (Maya 2, OpenAI)
  "keyring>=25.0",
]

[project.optional-dependencies]
maya2     = ["torch>=2.4"]                  # maya3 is not on PyPI (PyPI forbids URL deps); install it from git next to this extra
kokoro    = ["kokoro>=0.9.4; python_version < '3.13'", "torch>=2.4; python_version < '3.13'"]  # ADR-017
chatterbox= ["chatterbox-tts", "torch>=2.4"]
qa        = ["resemblyzer>=0.1.4"]          # or speechbrain; decided by ADR in S3-T03
cloud     = ["anthropic>=0.34"]
server    = ["fastapi>=0.112", "uvicorn[standard]>=0.30"]
mcp       = ["mcp>=1.2"]
dev       = ["pytest>=8.3", "pytest-cov>=5.0", "pytest-asyncio>=0.24", "pytest-timeout>=2.3",
             "hypothesis>=6.100", "respx>=0.21", "syrupy>=4.6", "ruff>=0.6", "mypy>=1.11",
             "pre-commit>=3.8", "pip-audit>=2.7", "pip-licenses>=5.0", "mkdocs-material>=9.5",
             "mkdocstrings[python]>=0.25", "types-PyYAML"]
```

System: `ffmpeg>=6.0` (libmp3lame, libopus, ebur128). CUDA 12.8 PyTorch wheels for Maya 2 on NVIDIA (per its install instructions).

### TypeScript / npm

```json
{
  "devDependencies": {
    "typescript": "^5.6",
    "vite": "^5.4",
    "preact": "^10.24",
    "vitest": "^2.1",
    "@playwright/test": "^1.48",
    "@axe-core/playwright": "^4.10",
    "eslint": "^9.12",
    "@typescript-eslint/eslint-plugin": "^8.8",
    "prettier": "^3.3",
    "license-checker": "^25.0"
  }
}
```

Pi extension: `@earendil-works/pi-agent-core` and `@sinclair/typebox` (verify current package names and versions at implementation time). Build tool: `bun>=1.1`.

### Models

| Model | Role | License | Notes |
|---|---|---|---|
| Maya 2 Native (2.5B, Maya Research) | Default TTS, cloning, 12 languages | Apache-2.0 | Built on Qwen3-1.7B-Base + Kyutai Mimi codec; 24 kHz; verify repo, flags and endpoint at implementation time |
| Kokoro-82M | CPU fallback | Apache-2.0 | English preset voices |
| Chatterbox | Optional clone backend | MIT | GPU recommended |
| qwen3 (via Ollama) | Script writing and translation | Apache-2.0 | 14B default; 0.6B for CI |
| resemblyzer | Speaker similarity | Apache-2.0 | |

---

## Out of Scope for v1

Create a GitHub issue with the `enhancement` label for each.

| Feature | Rationale for deferral |
|---|---|
| Desktop app (Tauri) | Studio on localhost covers review; revisit if non-engineer authors adopt it |
| Hosted SaaS (accounts, billing) | Local-first first; a hosted tier conflicts with zero-telemetry until designed carefully |
| Inline emotion tags | Maya 2 does not support them; add when a backend with tags is integrated (Maya1 adapter) |
| Forced alignment for word-level captions and read-along highlighting | High value for kids; needs an aligner model; v1.1 candidate |
| Multi-voice dialogue (narrator plus characters) | Needs script schema changes |
| Podcast RSS feed generation | Easy follow-on once manifests exist |
| Fine-tuning a personal voice | Zero-shot cloning is good enough for v1 |
| PDF, EPUB, and Google Docs sources | HTML and Markdown first |
| Redis-backed distributed job queue | Single GPU worker is enough for v1 |
| Background music library | Ship two stings only; users bring their own bed |
| Mobile apps / offline kid app (PWA) | Separate product built on top of published audio |
| Live streaming synthesis to the player | Needs server push; batch is fine for static sites |

---

## README Template

```markdown
# mr-audio-smith

*Every page deserves a voice.*

mr-audio-smith turns a web page into a realistic narration tuned for its listener, read in
your own cloned voice, generated on your own machine. It writes MP3, captions, and a one-tag
player you can drop into the page.

Part of the SnackOnAI smith family: mr-pixel-smith (images), mr-reel-smith (reels),
mr-motion-smith (motion), mr-audio-smith (audio).

## What it does

1. **Extracts** the real content of a page (no menus, no emoji names, no list numbers)
2. **Rewrites** it for a listener profile such as `kid-5` or `adult-commute`
3. **Speaks** it with Maya 2 Native in your cloned voice (or Kokoro on CPU, or OpenAI)
4. **Masters** it: natural pauses, gentle chime, consistent loudness
5. **Publishes** an MP3, WebVTT captions, and an embeddable player, and only re-renders what changed

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- ffmpeg 6+
- Ollama (for script writing) or an Anthropic / OpenAI-compatible key
- For Maya 2: an NVIDIA GPU with CUDA 12.8 drivers (Kokoro runs on CPU)

## Install

    uv tool install "mr-audio-smith[kokoro,qa]"
    mr-audio-smith doctor

## Quickstart

    # 1. Register your own voice (10 seconds, quiet room)
    mr-audio-smith voice add dad --clip my-voice.wav --name "Your Name" --relationship self

    # 2. Narrate a page for a five-year-old
    mr-audio-smith run https://example.com/letter.html --profile kid-5 --voice dad --inject letter.html

    # 3. Review and tweak in Studio
    mr-audio-smith studio

## Embed

    <audio-smith-player src="/media/audio/letter.mp3" captions="/media/audio/letter.vtt"
                        label="Listen to Dad read this letter" size="kid">
      <audio controls src="/media/audio/letter.mp3"></audio>
    </audio-smith-player>
    <script type="module" src="/media/audio/audio-smith-player.js"></script>

## Use from your agent

Claude Code, Goose, OpenCode: add the MCP server (`mr-audio-smith mcp`). Pi: install
`@mr-audio-smith/pi-extension`.

## Voice cloning ethics

Only clone your own voice, or a voice whose owner has given you written permission.
mr-audio-smith requires a consent record for every cloned voice.

## Build from source

    git clone https://github.com/mohnishbasha/mr-audio-smith && cd mr-audio-smith
    uv sync --all-extras --dev
    make lint typecheck test

## License

MIT © 2026 Serverless Ventures LLC. Model weights carry their own licenses; see
THIRD_PARTY_LICENSES.md.
```

---

## Implementation Notes for the Executing Agent

1. Your first action is Step 1: generate all five spec documents. No code before they are committed.
2. Spec documents supersede this prompt once they exist. Keep them current through the Spec Change Protocol.
3. Every sprint gate is a hard stop. Do not start a sprint until the previous gate is fully green.
4. TDD is mandatory. Write the failing test, watch it fail for the right reason, then implement.
5. The flagship use case is a parent narrating letters to a five-year-old. When a decision is ambiguous, choose what produces the warmest, clearest, safest listening experience for that child.
6. Never synthesize a cloned voice without a consent record. This check lives in core and cannot be bypassed by any flag.
7. Maya 2 Native is days old as of this prompt (released late October 2026). Before writing the backend, read its current README and model card, record the exact endpoint, voice cloning mechanism, package name (currently `maya3`), and flags in ARCHITECTURE.md, and adapt the adapter, not the interface.
8. Maya 2 has no emotion tags. Do not invent tags. Expressiveness comes from script wording, punctuation, pauses, and rate.
9. Synthesize per chunk. Never send a whole letter to a TTS model in one request.
10. Keep the TTSBackend and LLMProvider interfaces small. Model quirks belong in adapters.
11. Never re-serialize a user's HTML page. Inject by splicing between markers only.
12. Never shell out with strings. Argument arrays only, with timeouts.
13. No network access in unit tests. Use respx, the fake LLM provider, and the mock TTS backend.
14. Audio golden tests compare measured properties (duration, loudness, boundaries) with tolerances, never encoded bytes.
15. The player must work with JavaScript disabled. The native `<audio>` element inside it is the contract.
16. Do not add em dashes anywhere. The pre-commit hook will reject them.
17. Do not commit real voice clips, model weights, or generated audio of real people to the repository.
18. When uncertain about product behavior, update the spec with a proposal and an open question in the PR, rather than guessing silently in code.
19. Update `CHANGELOG.md` `[Unreleased]` in every user-facing PR.
20. At the end of every sprint, write the retrospective and tag the sprint before moving on.

---
## Appendix A: Integration Architecture Decision

| Decision | Choice | Why | Rejected alternatives |
|---|---|---|---|
| Core language | Python 3.12 | All viable open TTS models are PyTorch + Python | Rust core (would wrap Python anyway), TypeScript (no model runtimes) |
| Desktop shell | None in v1; Studio on localhost | Flagship user automates a static site; zero install friction | Tauri (adds Rust shell and signing for little gain in v1) |
| CLI runtime | Python + typer, installed with `uv tool` | Same process as the pipeline; no IPC | bun-compiled TS binary (default in portfolio, but cannot host PyTorch) |
| Default TTS | Maya 2 Native | Zero-shot cloning, 12 languages, Apache-2.0, OpenAI-compatible endpoint | Maya1 (no cloning), XTTS and F5-TTS (non-commercial weights), ElevenLabs default (cloud, paid, privacy) |
| CPU fallback | Kokoro-82M | Fast on CPU, Apache-2.0 | Piper (lower naturalness) |
| Script LLM | Ollama default | Local-first, matches portfolio default | Cloud-only (privacy) |
| Server | FastAPI with in-process job queue | Simple, typed, async | Celery + Redis (deferred) |
| Harness integration | MCP server (Python SDK) for Claude Code, Goose, OpenCode; Pi extension in TS calling the REST server | One server covers all MCP harnesses; Pi gets richer slash commands and streaming progress | Per-harness code for each MCP harness |
| Player | Dependency-free web component with native fallback | Drops into any static site, under 12 KB | React component (forces a framework on host pages) |
| Packaging | PyPI + npm + GHCR images (CPU amd64/arm64, CUDA amd64/arm64) + Helm | Covers laptops, GPU boxes, Kubernetes | Single fat image only |

**Deviation note:** The Serverless Ventures defaults are Tauri, Rust, and a bun-compiled TypeScript CLI. This product deviates deliberately because its core value lives in Python model runtimes. The deviation is recorded as ADR-001 and ADR-002. Rust and Tauri coding standards are replaced by the Python standards in this prompt.

---

## Appendix B: Repository Structure

```
mr-audio-smith/
├── .agent/
│   └── skills/
│       ├── run-tests/{SKILL.md,run.sh}
│       ├── check-types/{SKILL.md,run.sh}
│       └── narrate-fixture/{SKILL.md,run.sh}
├── .github/
│   ├── ISSUE_TEMPLATE/{task.yml,bug.yml}
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── dependabot.yml
│   └── workflows/{ci.yml,release.yml,docs.yml,gpu-integration.yml}
├── action/
│   ├── action.yml
│   └── narrate-changed.py
├── assets/
│   └── stings/{chime-soft.wav,chime-bright.wav,generate.py}
├── audio_smith/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── doctor.py
│   ├── errors.py
│   ├── fetch.py
│   ├── extract.py
│   ├── blocks.py
│   ├── site.py
│   ├── api.py
│   ├── profiles/{__init__.py,loader.py,schema.py,builtin/{kid-5,kid-8,adult-commute,adult-brief}.yaml}
│   ├── script/{writer.py,validate.py,translate.py,markdown.py,lexicon.py,prompts/{writer.md,translate.md}}
│   ├── llm/{base.py,ollama.py,anthropic.py,openai_compat.py,fake.py}
│   ├── tts/{base.py,registry.py,openai_compat.py,maya2.py,kokoro.py,chatterbox.py,mock.py}
│   ├── voices/{registry.py,consent.py,clipcheck.py}
│   ├── qa/{similarity.py,loudness.py}
│   ├── master/{assemble.py,ffmpeg.py,stings.py,tags.py,peaks.py}
│   ├── publish/{manifest.py,vtt.py,embed.py,inject.py}
│   ├── cache/{store.py,keys.py}
│   ├── server/{app.py,jobs.py,auth.py,models.py}
│   ├── mcp_server/{server.py,tools.py}
│   └── studio/{routes.py,static/}
├── charts/
│   └── mr-audio-smith/{Chart.yaml,values.yaml,templates/...}
├── deploy/
│   ├── docker/{Dockerfile.cpu,Dockerfile.cuda}
│   ├── docker-compose.local.yml
│   └── docker-compose.prod.yml
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DESIGN.md
│   ├── SPRINT_PLAN.md
│   ├── TEST_PLAN.md
│   ├── RETROSPECTIVES.md
│   ├── PERFORMANCE.md
│   ├── LISTENING_TESTS.md
│   ├── SECURITY_REVIEW.md
│   ├── guide/
│   └── reference/
├── examples/
│   ├── letters-to-a-child/
│   └── static-site/.github/workflows/narrate.yml
├── integrations/
│   ├── pi/{package.json,src/{index.ts,tools.ts,commands.ts},tests/}
│   ├── goose/toolkit.yaml
│   ├── opencode/opencode.json.example
│   └── claude-code/{README.md,skill/SKILL.md}
├── player/{package.json,src/{player.ts,waveform.ts,captions.ts,styles.css},tests/}
├── web/studio/{package.json,vite.config.ts,src/...}
├── schemas/{blocks,script,profile,manifest,voice}.schema.json
├── scripts/{check-versions.sh,bump-version.sh,extract-changelog.sh,create-issues.py,check-coverage.py,validate-fixtures.sh}
├── tests/{unit,integration,smoke,e2e,regression,fixtures}/
├── .coverage-thresholds.toml
├── .env.dev.example  .env.stage.example  .env.prod.example
├── .gitignore  .gitattributes  .editorconfig  .pre-commit-config.yaml
├── AGENTS.md  CLAUDE.md  SKILLS.md  SOUL.md
├── CHANGELOG.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md
├── LICENSE  THIRD_PARTY_LICENSES.md  README.md
├── Makefile  mkdocs.yml  pyproject.toml  uv.lock
└── audio-smith.toml.example
```

---

## Appendix C: Core Extraction (not applicable)

The standard Sprint 7 "Core extraction" refactor exists for products that start as a desktop app and later extract a shared library. mr-audio-smith is library-first from Sprint 1 (`audio_smith.api` is the core; CLI, Studio, server, and MCP are thin front doors). Enforce this continuously instead: front-door modules may import from `audio_smith.api` and models only, checked by an import-linter contract in CI (`import-linter` with a `forbidden` contract from `cli`, `server`, `mcp_server`, `studio` to internal stage modules).

## Appendix D: CLI (delivered in Sprints 0 to 4)

The CLI is the primary artifact and ships with v1.0.0, so there is no separate CLI sprint. Sprint numbering below therefore continues at 7 with Server and MCP.

---

## Appendix E: Sprint 7: Server and MCP

**Milestone:** Sprint 7: Server and MCP
**Duration:** 1 week
**Goal:** mr-audio-smith runs as a service other machines and agents can call.

### S7-T01: REST server with job queue
- **Labels:** type: feature, area: server, priority: p0, size: L, sprint: 7
- **Description:** FastAPI app per ARCHITECTURE REST contract. Single GPU worker consuming an asyncio queue; jobs persisted to SQLite (`jobs.db`) so restarts keep history; artifacts under `OUT_DIR/jobs/{id}`. Progress reported per stage and chunk.
- **AC:** FR-023 ACs; jobs survive restart; concurrent submissions queue in order
- **Depends on:** Sprint 6

### S7-T02: Auth, limits, health
- **Labels:** type: security, area: server, priority: p0, size: M, sprint: 7
- **Description:** Bearer token required on non-localhost bind; rate limiting; `/healthz`, `/readyz` (Maya 2 reachable, model loaded, ffmpeg present); problem+json errors.
- **AC:** auth tests; readiness flips when backend is down
- **Depends on:** S7-T01

### S7-T03: MCP server
- **Labels:** type: feature, area: mcp, priority: p0, size: L, sprint: 7
- **Description:** Official Python MCP SDK; transports stdio and streamable HTTP. Tools:

```
mr_audio_smith_narrate      {source, profile?, voice?, backend?, langs?, inject_path?}
                            -> {manifest_path, tracks:[{lang, file, duration_s}], warnings}
                            (long-running: emits progress notifications per stage)
mr_audio_smith_script       {source, profile?} -> {script_path, chunks, est_minutes}
mr_audio_smith_render       {script_path, chunks?, voice?, backend?} -> {files}
mr_audio_smith_list_voices  {} -> [{id, display_name, backends, cloned}]
mr_audio_smith_list_profiles{} -> [{id, version, description}]
mr_audio_smith_list_backends{} -> [{id, available, languages, cloning, license}]
mr_audio_smith_status       {} -> doctor report as JSON
mr_audio_smith_recommend    {source | description} -> {profile, backend, reason}
```

  Tool descriptions state that cloning requires a registered voice with consent, so agents do not try to bypass it. File paths returned are absolute.
- **AC:** FR-024 ACs; MCP inspector lists all tools with valid schemas; integration test drives `narrate` with mocks over stdio
- **Depends on:** S7-T01

### S7-T04: Remote mode for CLI and Action
- **Labels:** type: feature, area: cli, priority: p1, size: M, sprint: 7
- **Description:** `--server URL --token ...` makes `run` and `site` submit jobs remotely and download artifacts; the GitHub Action uses this path when `server-url` is set.
- **AC:** end-to-end test against a local server process
- **Depends on:** S7-T02

### Sprint 7 Gate (hard stop)
- [ ] Server runs on the GPU box; a laptop narrates a page through it
- [ ] MCP tools work from Claude Code via stdio
- [ ] Coverage for `server` and `mcp_server` at or above targets
- [ ] Retrospective written, `sprint-7-complete` tagged

---

## Appendix F: Sprint 8: Harness Integrations

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
- **Description:** TypeBox schemas mirroring MCP tools; slash commands `/narrate <url> [profile] [voice]`, `/voices`, `/audio-status`; streams job progress through `onUpdate`; context extension injects available voices and profiles at session start; config via `AUDIO_SMITH_SERVER_URL` and token.
- **AC:** vitest unit tests with mocked server; manual test in Pi recorded in TEST_PLAN
- **Depends on:** Sprint 7

### S8-T02: Goose toolkit
- **Labels:** type: feature, area: harness, priority: p1, size: S, sprint: 8
- **Description:** `toolkit.yaml` launching `mr-audio-smith mcp --transport stdio`; README section.
- **AC:** smoke test listing tools from Goose
- **Depends on:** Sprint 7

### S8-T03: OpenCode config
- **Labels:** type: docs, area: harness, priority: p1, size: S, sprint: 8
- **Description:** Config snippet and README section.
- **AC:** smoke test listing tools from OpenCode
- **Depends on:** Sprint 7

### S8-T04: Claude Code skill
- **Labels:** type: feature, area: harness, priority: p1, size: M, sprint: 8
- **Description:** A skill (`SKILL.md`) teaching Claude Code when and how to call the MCP tools, the consent rule, how to review a script before rendering, and how to inject into a static site; `claude mcp add` instructions.
- **AC:** skill loads; a scripted session narrates the fixture page
- **Depends on:** Sprint 7

### S8-T05: Harness smoke tests in CI
- **Labels:** type: test, area: ci, priority: p2, size: M, sprint: 8
- **Description:** `harness-smoke-tests` job on staging and release: MCP stdio handshake and `tools/list`; Pi extension unit tests.
- **AC:** job green on staging
- **Depends on:** S8-T01 to S8-T04

### Sprint 8 Gate (hard stop)
- [ ] Each harness narrates the fixture page with mocks in a recorded session
- [ ] Docs list setup steps for all four harnesses
- [ ] Retrospective written, `sprint-8-complete` tagged

---

## Appendix G: Sprint 9: Packaging and Deployment

**Milestone:** Sprint 9: Packaging
**Duration:** 1 week
**Goal:** Three deployment tiers, all documented and tested.

### Tier 1: Local binary
- `uv tool install mr-audio-smith[...]` (primary); `pipx` documented as an alternative.
- Maya 2 server run locally per its README; `mr-audio-smith doctor` verifies it.

### Tier 2: Docker Compose

`deploy/docker-compose.local.yml`

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

### Tier 3: Kubernetes via Helm (`charts/mr-audio-smith`)

- **StatefulSet `maya2`**: GPU (`nvidia.com/gpu: 1`) via NVIDIA device plugin, PVC `models` (50Gi), init container pre-downloads and checksums weights, readiness probe on `/health`.
- **StatefulSet `ollama`** (optional, `ollama.enabled`): PVC 100Gi, init job pulls the script model. Alternatively point at an existing vLLM OpenAI-compatible endpoint (on NVIDIA Grace arm64 nodes, use `nvcr.io/nvidia/vllm-openai:latest`).
- **Deployment `audio-smith`**: API layer, HPA on CPU and queue depth (custom metric), PVC `cache` (ReadWriteMany if replicas > 1) and `voices` (secret-like, 0700), Secret for `AUDIO_SMITH_SERVER_TOKEN`.
- **Ingress**: TLS, `proxy-read-timeout: 600`, `proxy-body-size: 10m`, auth annotation.
- **NetworkPolicy**: only audio-smith may reach maya2 and ollama.
- Values for k3s with Cilium on a 2-node GPU cluster provided as `values-k3s-gpu.yaml`.

### S9-T01: Dockerfiles
- **Labels:** type: chore, area: packaging, priority: p0, size: L, sprint: 9
- **Description:** `Dockerfile.cpu` (python slim, ffmpeg, Kokoro extra, non-root) and `Dockerfile.cuda` (NVIDIA CUDA 12.8 runtime base, torch CUDA wheels), both multi-arch amd64 and arm64; build cache in GHA.
- **AC:** images run `doctor` green; CPU image under 1.5 GB
- **Depends on:** Sprint 7

### S9-T02: Compose files and model pre-puller
- **Labels:** type: chore, area: packaging, priority: p0, size: M, sprint: 9
- **AC:** `docker compose -f deploy/docker-compose.local.yml up` narrates the fixture page via the API on a GPU host
- **Depends on:** S9-T01

### S9-T03: Helm chart
- **Labels:** type: chore, area: packaging, priority: p0, size: L, sprint: 9
- **AC:** `helm lint` and `helm template` pass; `ct install` in kind with the CPU profile (mock backend); manual install on the GPU cluster documented
- **Depends on:** S9-T01

### S9-T04: Signing and publishing
- **Labels:** type: ci, area: packaging, priority: p1, size: M, sprint: 9
- **Description:** cosign keyless signing for images and chart; SBOM attestation; release workflow publishes images and chart.
- **AC:** `cosign verify` succeeds for released images
- **Depends on:** S9-T02, S9-T03

### Sprint 9 Gate (hard stop)
- [ ] All three tiers documented and tested
- [ ] Signed images and chart published for the current version
- [ ] Retrospective written, `sprint-9-complete` tagged; release v1.1.0

---

## Appendix H: Complete Sprint Overview

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

---

## Appendix I: Modularity Principles

1. **Stages are pure functions over files.** Each stage reads its inputs from typed models or files and writes typed outputs. Any stage can be re-run alone.
2. **Interfaces are tiny.** `TTSBackend` has three methods and capabilities; `LLMProvider` has two. Adding a backend is one file plus a registry entry plus tests.
3. **Adapters absorb quirks.** Marker handling, voice mapping, and language codes for a model live in its adapter, never in the pipeline.
4. **Front doors are thin.** CLI, Studio, REST, MCP, Action, and Pi extension call `audio_smith.api` only (enforced by import-linter).
5. **Profiles are data.** No audience logic in code beyond reading profile fields. New audiences need no release.
6. **Caching is a cross-cutting concern** with one key module; no stage computes its own ad hoc cache keys.
7. **Safety in core.** Consent, SSRF guard, path guard, and license guard live below every front door.
8. **Optional extras stay optional.** Base install has no torch; each backend imports its heavy dependencies lazily and reports a clear doctor hint when missing.

---

## Appendix J: Test Infrastructure and Maintenance

### Coverage targets

```toml
# .coverage-thresholds.toml
[python]
"audio_smith/extract.py" = 90
"audio_smith/blocks.py" = 95
"audio_smith/script" = 90
"audio_smith/profiles" = 90
"audio_smith/voices" = 90
"audio_smith/tts" = 85
"audio_smith/master" = 85
"audio_smith/publish" = 90
"audio_smith/cache" = 90
"audio_smith/qa" = 80
"audio_smith/server" = 80
"audio_smith/mcp_server" = 80
"audio_smith/cli.py" = 75
overall = 85

[typescript]
"player/src" = 85
"web/studio/src" = 75
"integrations/pi/src" = 70
```

### Test types

| Type | When | Runner | Location |
|---|---|---|---|
| Unit | Pure logic, no I/O, no network | pytest / vitest | `tests/unit/`, `player/tests/` |
| Integration | Real ffmpeg, Ollama, Kokoro, Maya 2 (GPU) | pytest -m integration | `tests/integration/` |
| Smoke | Minimal end-to-end sanity | `tests/smoke/smoke.sh` | `tests/smoke/` |
| E2E | Player and Studio flows | Playwright | `tests/e2e/` |
| Regression | Every bug fixed gets one | pytest / vitest | `tests/regression/` |
| Listening | Human evaluation per release | TEST_PLAN protocol | `docs/LISTENING_TESTS.md` |

### CI pipeline structure

```yaml
jobs:
  lint-and-typecheck:   # ubuntu, macos, windows: ruff, mypy, eslint, tsc, em dash check
  unit-tests:           # depends on lint; 3 OS x py3.12/3.13; vitest for player/studio/pi
  coverage:             # depends on unit; ubuntu; threshold script; Codecov upload
  integration-tests:    # depends on unit; ubuntu; ffmpeg + Ollama tiny model + Kokoro CPU
  e2e-tests:            # depends on integration; ubuntu; Playwright + axe
  check-versions:       # PRs to staging and main
  smoke:                # depends on unit; mock end to end
  gpu-integration:      # self-hosted [gpu]; Maya 2; PRs to staging/main + dispatch
  harness-smoke-tests:  # staging and release only
```

### Fixture maintenance
- `scripts/validate-fixtures.sh` re-runs extraction on fixture pages and fails if block snapshots drift without a snapshot update in the same PR.
- Recorded LLM fixtures are keyed by prompt hash; when a prompt template version changes, re-record with `make record-llm` (requires Ollama) and review diffs.
- Fixture voice clips are synthetic tones or the maintainer's own voice with a consent record; never third-party voices.
- Golden audio tolerances: duration plus or minus 5 ms per join, loudness plus or minus 1 LU, boundaries plus or minus 10 ms.

### Flake policy
A flaky test is quarantined with `@pytest.mark.flaky_quarantine` and a linked issue within 24 hours, fixed within the sprint. Quarantine never exceeds 5 tests.

---

## Appendix K: Agent Repository Files (content specification)

### `AGENTS.md`

```markdown
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
```

### `CLAUDE.md`

```markdown
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
```

### `SKILLS.md`

```markdown
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
```

### `.agent/skills/run-tests/SKILL.md` and `run.sh`

```markdown
---
name: run-tests
description: Run lint, unit tests, and coverage thresholds for mr-audio-smith.
---
Run `./run.sh`. Passes when lint, unit tests, and coverage thresholds all pass.
On failure, read the first failing test, fix the cause, and re-run.
```

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
make lint
make test
make coverage
```

### `.agent/skills/check-types/SKILL.md` and `run.sh`

```markdown
---
name: check-types
description: Run mypy --strict and tsc --noEmit across all packages.
---
Run `./run.sh`. Fix every error; do not add type ignores without an error code and comment.
```

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
make typecheck
```

### `.agent/skills/narrate-fixture/SKILL.md` and `run.sh`

```markdown
---
name: narrate-fixture
description: Narrate the reference letter fixture end to end with mock LLM and mock TTS.
---
Run `./run.sh`. Passes when out/letter-calm/ contains mp3, vtt, embed.html, and a manifest
that validates against schemas/manifest.schema.json.
```

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock --out out --force
uv run python -c "import json,jsonschema; jsonschema.validate(json.load(open('out/letter-calm/letter-calm.manifest.json')), json.load(open('schemas/manifest.schema.json')))"
ls out/letter-calm/*.mp3 out/letter-calm/*.vtt out/letter-calm/*.embed.html
```

### `SOUL.md`

```markdown
# Soul

## Identity
You are building mr-audio-smith, an open-source tool that gives written pages a voice. Its
first listener is a five-year-old hearing letters from his father. Build for that child.

## What this project values
- Warmth and clarity over technical flash
- Local-first and private by default
- Correctness proven by tests, which are permanent
- Specs first; code follows the spec
- Small interfaces and honest documentation

## Hard constraints
- Never clone a voice without a consent record, and never weaken that check.
- Never send page text, scripts, or audio to a cloud service unless the user configured it.
- Never invent capabilities a model does not have (for example emotion tags on Maya 2).
- Never modify user HTML outside the injection markers.
- Never merge code without tests that fail without it.
- Never add telemetry.
- Never use em dashes.

## What good work looks like
A parent runs one command and their child hears a narration that sounds like them, paced
for small ears, with nothing strange read aloud. The code that made it is small, typed,
tested, and documented.

## When uncertain
Stop and write the question into the relevant spec doc as an open question in your PR.
Prefer the choice that is safer for the listener and easier to undo.

## Tone
Plain, kind, specific. Explain why, not just what.
```

---

*End of build prompt.*
