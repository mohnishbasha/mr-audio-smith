# mr-audio-smith: Product Requirements Document

Version: 1.0 (draft for v1). Date: 2026-11-01. Repo: `mohnishbasha/mr-audio-smith`. License: MIT.

This document is the source of truth for product behavior. Structure and contracts live in `docs/ARCHITECTURE.md`; the player and Studio visuals live in `docs/DESIGN.md`. Changes follow the Spec Change Protocol.

---

## 1. Overview

### 1.1 Problem

Written content on personal sites, newsletters, and blogs is only reachable by readers. Young children cannot read it yet, commuters cannot read while driving, and many people simply prefer listening. Existing text-to-speech readers read the page verbatim: they pronounce headings, list numbers, emoji names, and navigation, in a generic voice, at one pace, for one imagined adult listener. Cloud narration services sound better but cost money per character, send private family content to third parties, and do not adapt the text to the listener.

### 1.2 Solution

mr-audio-smith is a local-first pipeline with five stages:

1. Extract the real content of a page.
2. Rewrite it into a listening script for a named audience profile.
3. Synthesize it paragraph by paragraph (chunk by chunk) with a pluggable TTS backend (default: Maya 2 Native with the author's cloned voice).
4. Master it into a consistent, pleasant listening experience.
5. Publish an MP3 plus captions plus a drop-in player.

Every artifact is cached by content hash so rebuilding a whole site only renders what changed.

### 1.3 Flagship use case

A parent publishes letters to their five-year-old on a personal site (reference site: `https://www.aadhish.us/messages-from-dad.html`, example letter: `https://www.aadhish.us/letter-calm-in-the-chaos.html`). Each letter must get an audio version read in the parent's own cloned voice, rewritten for a five-year-old listener, embedded on the letter page as a "Listen" option, and regenerated automatically when a letter is added or edited. Every design decision in this document is tested against this use case first.

### 1.4 Product principles

- Local-first: no page text, script, or audio leaves the machine with default config.
- Consent-first: no voice is cloned without a recorded consent.
- Incremental: only changed content is re-rendered.
- Reviewable: a human can read and edit the script before audio is rendered.
- Calm: the player is warm, quiet, and never competes with the page.

---

## 2. Personas

| ID | Persona | Goal | Technical level |
|---|---|---|---|
| P-1 | **Parent author** (flagship) | Letters to their child, narrated in their own voice, on their own site | Engineer comfortable with CLI and GitHub Actions |
| P-2 | **Newsletter writer** | Audio edition of each issue for subscribers who listen | Comfortable with CLI, may use the hosted player only |
| P-3 | **Agent operator** | Ask Claude Code, Pi, Goose or OpenCode to "narrate this page" and get files back | Uses agent harnesses daily |
| P-4 | **Platform team** | Run narration as a shared service for many sites | Kubernetes, GPUs |
| P-5 | **Listener** (child or adult) | Press play, hear a warm, clear, well-paced narration | Non-technical; for P-1 a five-year-old |

---

## 3. User stories

Each story lists the functional requirements that satisfy it. Every story maps to at least one FR (see the traceability matrix in section 11).

**US-001** As a parent author, I run one command with a page URL and get an MP3 of that page narrated for a five-year-old, so my child can listen to my letter.
Maps to: FR-001, FR-002, FR-004, FR-005, FR-006, FR-009, FR-012, FR-014, FR-016

**US-002** As a parent author, I register a short recording of my own voice once, so every narration sounds like me.
Maps to: FR-011, FR-010, FR-013

**US-003** As a parent author, I review and edit the generated script before audio is rendered, so nothing is said that I did not intend.
Maps to: FR-005, FR-006, FR-022

**US-004** As a parent author, I re-render a single paragraph after editing it, without re-rendering the whole letter.
Maps to: FR-012, FR-020, FR-022

**US-005** As a parent author, I mark sections of my page (for example "A grown-up note") to be skipped or rendered as a separate parent track.
Maps to: FR-002, FR-026

**US-006** As a parent author, I add a player to my letter page with one snippet, so my child can press "Listen to Dad".
Maps to: FR-017, FR-018, FR-015

**US-007** As a parent author, I get an additional language version (for example Hindi) in my own voice, so my child hears the letter in a heritage language.
Maps to: FR-008, FR-010, FR-017

**US-008** As a parent author, a GitHub Action narrates every new or changed letter automatically when I push, so I never run anything by hand.
Maps to: FR-025, FR-003, FR-020

**US-009** As a newsletter writer, I define my own audience profile (for example "commuter, 8 minutes max") in YAML without changing code.
Maps to: FR-004, FR-005

**US-010** As a newsletter writer, I switch the TTS backend (local Maya 2, Kokoro on CPU, OpenAI cloud) with one flag.
Maps to: FR-009, FR-010

**US-011** As a listener, the narration has natural pauses, consistent volume, a short intro chime, and never reads emoji names, list numbers, or navigation text.
Maps to: FR-002, FR-005, FR-006, FR-014

**US-012** As a listener with hearing differences, I can turn on captions in the player.
Maps to: FR-015, FR-017

**US-013** As an agent operator, I call mr_audio_smith_narrate from my harness and receive file paths and a duration.
Maps to: FR-024, FR-016

**US-014** As a platform team, I deploy mr-audio-smith as an HTTP service on Kubernetes with GPU scheduling and a persistent cache.
Maps to: FR-023, FR-020, FR-021

**US-015** As a parent author, the tool refuses to clone any voice that has not been registered with a consent record, so it cannot be misused to imitate someone.
Maps to: FR-011, FR-009, FR-010

**US-016** As a parent author, I narrate every letter linked from an index page in one batch command.
Maps to: FR-019, FR-003, FR-020

**US-017** As a parent author, I compare two takes of a paragraph side by side in a local review UI and keep the better one.
Maps to: FR-022, FR-013, FR-012

**US-018** As any user, I run `mr-audio-smith doctor` and get a clear report of what is missing (ffmpeg, GPU, model weights, voice clip quality) before anything fails mid-run.
Maps to: FR-021, FR-011

---

## 4. Functional requirements

Conventions: "AC" items are acceptance criteria and each is a testable checkbox. Items prefixed "Prompt AC" are carried over verbatim from the source prompt; items prefixed "Expanded" add detail that engineers need to implement and test.

### FR-001 Fetch page

Fetch an http(s) URL or read a local .html/.md file.

- [ ] Prompt AC: honors a configurable timeout (default 20s) and max size (default 5 MB)
- [ ] Prompt AC: rejects non-http(s) schemes
- [ ] Prompt AC: sends a descriptive User-Agent
- [ ] Prompt AC: local files are read without network access
- [ ] Expanded: timeout and max size are settable via `audio-smith.toml`, environment, and CLI flags, with CLI taking precedence
- [ ] Expanded: SSRF guard blocks 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fc00::/7, fe80::/10 and cloud metadata addresses; DNS is resolved once and the IP pinned for the connection
- [ ] Expanded: a maximum redirect count is enforced and each redirect target is re-checked against the guard
- [ ] Expanded: exceeding max size aborts the download and reports the limit, not a partial parse
- [ ] Expanded: HTML is parsed only, never rendered; no JavaScript engine runs in the pipeline
- [ ] Expanded: local `.html` and `.md` paths are resolved and must exist; unsupported extensions give a clear error

### FR-002 Extract narratable content

Extraction order: (1) element with [data-narrate] attribute, (2) <article>, (3) trafilatura main-content extraction, (4) readability fallback.

- [ ] Prompt AC: navigation, header, footer, scripts, styles, forms are excluded
- [ ] Prompt AC: emoji are stripped
- [ ] Prompt AC: elements with data-narrate="skip" are excluded
- [ ] Prompt AC: elements with data-narrate="parent" go to the parent track
- [ ] Prompt AC: output is an ordered list of typed blocks: title, heading, paragraph, list_item, quote, signature
- [ ] Expanded: blocks carry stable ids derived from order and text so downstream stages can reference them
- [ ] Expanded: elements marked `data-narrate-verbatim` are flagged on their block so the script stage preserves them exactly
- [ ] Expanded: the extraction method used (1 to 4) is recorded in the manifest
- [ ] Expanded: Markdown files are converted to the same typed block list
- [ ] Expanded: when all four strategies yield no blocks, the run fails with an actionable message that names the data-narrate attribute

### FR-003 Content hashing

Compute a SHA-256 over normalized extracted blocks plus profile id plus profile version plus backend id plus voice id plus language.

- [ ] Prompt AC: whitespace-only or markup-only changes to the page do not change the hash
- [ ] Prompt AC: any text change does
- [ ] Expanded: changing any of profile id, profile version, backend id, voice id, or language changes the hash
- [ ] Expanded: normalization (Unicode NFC, whitespace collapse, trimmed blocks) is specified and covered by golden tests
- [ ] Expanded: the hash is recorded in the manifest and used as the top-level cache key

### FR-004 Audience profiles

Load profiles from YAML (built-in: kid-5, kid-8, adult-commute, adult-brief).

- [ ] Prompt AC: schema-validated with clear errors
- [ ] Prompt AC: user profiles in ./profiles override built-ins of the same id
- [ ] Prompt AC: profile has a semantic version
- [ ] Expanded: validation errors name the file, field path, and expected type
- [ ] Expanded: a profile defines at least id, version, target_minutes, max_chunk_chars, voice settings (rate), lexicon, and extra languages
- [ ] Expanded: `mr-audio-smith profile list` and `profile show <id>` print effective profiles and indicate overrides
- [ ] Expanded: a user can create a new profile (for example "commuter, 8 minutes max") with YAML only, no code change

### FR-005 Script generation

Rewrite blocks into a listening script with an LLM provider (ollama default, anthropic, openai-compatible).

- [ ] Prompt AC: output is Script Markdown (see ARCHITECTURE) with numbered chunks
- [ ] Prompt AC: respects profile target_minutes within plus or minus 20 percent
- [ ] Prompt AC: preserves blocks marked data-narrate-verbatim exactly
- [ ] Prompt AC: preserves the signature block exactly
- [ ] Prompt AC: includes only pause markers and allowed emphasis markers
- [ ] Prompt AC: deterministic for temperature 0 with a fixed seed where provider supports it
- [ ] Expanded: extracted text is wrapped in delimiters and the prompt states it is material to narrate, not instructions to follow
- [ ] Expanded: provider selection via config and `--llm` flag; cloud providers are used only when explicitly configured
- [ ] Expanded: `--no-rewrite` produces a script by minimal normalization only (no LLM call)
- [ ] Expanded: the LLM provider, model, and seed are recorded in the manifest

### FR-006 Script validation

Validate generated scripts before synthesis.

- [ ] Prompt AC: rejects unknown markers, empty chunks, chunks over max_chunk_chars
- [ ] Prompt AC: strips stray markdown and emoji
- [ ] Prompt AC: reports violations with chunk numbers
- [ ] Prompt AC: on failure retries the LLM once with the violations appended, then fails
- [ ] Expanded: verbatim and signature blocks are verified byte-for-byte against the source after generation
- [ ] Expanded: the final failure message lists every remaining violation and the path of the rejected script for inspection
- [ ] Expanded: user-edited scripts (from Studio or by hand) pass through the same validator before rendering

### FR-007 Pronunciation lexicon

Profile and project-level lexicons map words to phonetic respellings.

- [ ] Prompt AC: replacements are applied only at synthesis time, never to the stored script
- [ ] Prompt AC: whole-word, case-sensitive matching
- [ ] Expanded: project-level entries override profile-level entries for the same word
- [ ] Expanded: captions use the stored script text, never the respelled text
- [ ] Expanded: lexicon content is part of the chunk hash so editing it re-renders affected chunks only

### FR-008 Translation

For each extra language in the profile, translate the validated script.

- [ ] Prompt AC: chunk boundaries and pause markers are preserved one to one
- [ ] Prompt AC: translated script stored as {slug}.{lang}.script.md
- [ ] Expanded: translated scripts pass the same validator as the source script
- [ ] Expanded: languages not supported by the selected backend fail at preflight, not mid-render
- [ ] Expanded: each translated script gets its own chunk hashes and its own track and captions
- [ ] Expanded: the voice used for a translation is the same registered voice (cross-lingual cloning) when the backend supports it

### FR-009 TTS backend interface

Pluggable backends behind one interface: preflight(), list_voices(), synth(chunk, voice, params) -> PCM audio, capabilities().

- [ ] Prompt AC: backends: maya2 (default), kokoro (CPU fallback), openai (cloud), openai_compat (any OpenAI-compatible /v1/audio/speech server), mock (tests)
- [ ] Expanded: backend is selected with one flag (`--backend`) or config key
- [ ] Expanded: `capabilities()` reports languages, cloning support, sample rate, and max chunk size so callers can fail early
- [ ] Expanded: backends refuse clone requests for voices that are not registered with consent (enforced in core, not only in adapters)
- [ ] Expanded: the `mock` backend is deterministic and requires no model weights, GPU, or network
- [ ] Expanded: Kokoro is an optional extra constrained to Python below 3.13; the doctor hints to use Python 3.12 otherwise
- [ ] Expanded: using openai (cloud) triggers a "cloud providers active" warning in `doctor` and in the run summary

### FR-010 Maya 2 Native backend

Synthesize via the local Maya 2 Native server's OpenAI-compatible speech endpoint, with optional in-process mode via the Python package.

- [ ] Prompt AC: supports built-in voices and zero-shot cloning from a registered reference clip
- [ ] Prompt AC: supports all Maya 2 languages
- [ ] Prompt AC: returns 24 kHz mono PCM
- [ ] Expanded: default server URL is `http://127.0.0.1:8080/v1` (`AUDIO_SMITH_MAYA2_URL`); this corrects the 8000 default in the source prompt because the Maya 2 server listens on 8080
- [ ] Expanded: synthesis posts to `/v1/audio/speech` with model `maya3`, `input`, `voice`, `language`, `response_format`, `normalize`, `seed`, and sampling params
- [ ] Expanded: `speed` is always sent as 1.0 because the server requires it; the profile's speaking rate is applied after synthesis (ffmpeg atempo) in the adapter or mastering stage (ADR-016)
- [ ] Expanded: same seed, text, and voice produce the same audio; the seed per take is recorded
- [ ] Expanded: languages supported: as, bn, en, gu, hi, kn, ml, mr, or, pa, ta, te; 20 built-in voices: Ahana, Vaidehi, Malini, Charvi, Jahnavi, Anirban, Nakul, Vasant, Siddhant, Satvik, Abhay, Nivedita, Ishwari, Ritvik, Vrinda, Sreekar, Kayal, Shaunak, Akshat, Tanushree
- [ ] Expanded: before the first synthesis with a cloned voice the adapter registers the consented clip via `POST /v1/voices` with voice_id `as-{voice_id}-{clip_hash[:8]}`, mode `icl_spk`, replace=false; an already-exists or 409 response is treated as success
- [ ] Expanded: `GET /health` is used by preflight; 503 means still loading and the adapter waits with bounded backoff
- [ ] Expanded: 503 overloaded responses honor `retry_after`; 400 errors surface the server message and are not retried
- [ ] Expanded: in-process mode uses package `maya3` (`Maya3TTS.from_pretrained`) when selected by config
- [ ] Expanded: preflight reports clearly that Maya 2 needs a Linux NVIDIA GPU (about 8 GB VRAM) and that Apple MPS is not supported

### FR-011 Voice registry and consent

Voices are registered with `mr-audio-smith voice add`.

- [ ] Prompt AC: registration requires a reference clip and a consent record (name, relationship "self" or "has written permission", date, statement)
- [ ] Prompt AC: backends refuse clone requests for unregistered voices
- [ ] Prompt AC: clip quality is checked (duration 3 to 30 s, mono or downmixable, sample rate at least 16 kHz, clipping under 0.1 percent, SNR estimate at least 25 dB)
- [ ] Expanded: reference clips are stored with `0600` permissions and are uploaded nowhere except the configured local or self-hosted TTS server
- [ ] Expanded: manifests record the voice id, never the clip or the consent statement
- [ ] Expanded: `voice list`, `voice show`, and `voice remove` exist; removal deletes the clip and the consent record together
- [ ] Expanded: each quality check failure names the measured value and the threshold
- [ ] Expanded: README and CLI help state plainly: only clone your own voice or a voice you have written permission to use

### FR-012 Chunked synthesis

Synthesize one script chunk at a time.

- [ ] Prompt AC: chunk results cached by chunk hash
- [ ] Prompt AC: failed chunks retried up to 2 times with backoff
- [ ] Prompt AC: partial progress survives interruption and resumes
- [ ] Expanded: the chunk hash covers text, voice, backend, language, seed, params, and lexicon
- [ ] Expanded: retries distinguish retryable errors (timeouts, 503) from fatal errors (400, unknown voice)
- [ ] Expanded: a single chunk failure never discards completed chunks; the final error names the failed chunk numbers
- [ ] Expanded: `render --chunk N` re-renders exactly one chunk without touching others

### FR-013 Voice consistency QA

Compute speaker embeddings per chunk and compare to the reference clip (or to chunk 1 for built-in voices).

- [ ] Prompt AC: chunks below the similarity threshold (default 0.75) are re-rendered with a new seed up to takes_per_chunk times
- [ ] Prompt AC: the best take is kept
- [ ] Prompt AC: report lists scores
- [ ] Expanded: embeddings use resemblyzer from the optional `qa` extra, lazy-imported (ADR-015)
- [ ] Expanded: when resemblyzer is absent QA is skipped and the manifest carries an explicit warning, never a silent pass
- [ ] Expanded: all takes and their scores are retained for comparison in Studio

### FR-014 Mastering

Join chunks, insert silences for pause markers, add optional intro and outro stings, optional music bed with sidechain ducking, normalize loudness, encode.

- [ ] Prompt AC: integrated loudness -16 LUFS plus or minus 1, true peak at or below -1.5 dBTP
- [ ] Prompt AC: MP3 128 kbps mono 44.1 kHz by default; optional Opus
- [ ] Prompt AC: ID3 tags: title, artist (author), album (site name), date, cover art
- [ ] Expanded: ffmpeg 6 or newer is required and checked by preflight
- [ ] Expanded: two stings ship by default (intro chime and outro); music beds are user supplied
- [ ] Expanded: pause markers map to documented silence durations
- [ ] Expanded: peak data (28 values, 0 to 100) is computed during mastering and written to the manifest for the player waveform
- [ ] Expanded: measured loudness and true peak are recorded in the manifest

### FR-015 Captions

Produce WebVTT from chunk timings.

- [ ] Prompt AC: one cue per sentence
- [ ] Prompt AC: cue boundaries within 150 ms of audio
- [ ] Prompt AC: text from the narrated script (not the original page)
- [ ] Expanded: one VTT file per language track
- [ ] Expanded: cue timings account for inserted pauses, stings, and any atempo adjustment
- [ ] Expanded: pronunciation respellings never appear in cues
- [ ] Expanded: WebVTT passes a standards validator in CI

### FR-016 Manifest

Write {slug}.manifest.json with versions, hashes, backend, voice id, languages, durations, QA scores, and file names.

- [ ] Prompt AC: validates against the published JSON Schema
- [ ] Expanded: per-stage timings and the extraction method are included (NFR-010)
- [ ] Expanded: peaks array, loudness, true peak, and warnings are included
- [ ] Expanded: no secrets, clip data, or consent statements appear in the manifest
- [ ] Expanded: manifest carries a schema version and the schema file is published in the repo and package

### FR-017 Embed snippet

Produce {slug}.embed.html using the <audio-smith-player> web component, with a plain <audio> fallback inside it.

- [ ] Prompt AC: works with JavaScript disabled
- [ ] Prompt AC: includes captions track
- [ ] Prompt AC: language toggle when more than one language exists
- [ ] Expanded: the snippet sets `src`, `captions`, `label`, `peaks`, and (for multi-language) `tracks` attributes per the contract in DESIGN.md
- [ ] Expanded: the component is under 12 KB gzipped with no dependencies (NFR-011)
- [ ] Expanded: no autoplay, no download button by default, no external network calls from the player
- [ ] Expanded: playback position is the only thing stored in localStorage, inside try/catch

### FR-018 Inject mode

`--inject` writes the embed snippet into a local HTML file between <!-- audio-smith:start --> and <!-- audio-smith:end --> markers.

- [ ] Prompt AC: idempotent
- [ ] Prompt AC: creates markers after the configured selector if absent
- [ ] Prompt AC: never modifies anything outside the markers
- [ ] Prompt AC: dry-run prints a unified diff
- [ ] Expanded: a second run with unchanged output produces a byte-identical file
- [ ] Expanded: if the configured selector is not found, the run fails with a message and writes nothing
- [ ] Expanded: output paths are resolved and verified to be inside the output root

### FR-019 Batch site mode

`mr-audio-smith site <index-url> --match <glob>` narrates every matching linked page.

- [ ] Prompt AC: same-origin links only
- [ ] Prompt AC: respects a max-pages limit
- [ ] Prompt AC: skips unchanged pages by hash
- [ ] Prompt AC: prints a summary table
- [ ] Expanded: summary table lists page, status (rendered, skipped, failed), duration, and elapsed time
- [ ] Expanded: one page failing does not abort the batch; the exit code reflects any failure
- [ ] Expanded: the SSRF guard applies to every discovered link

### FR-020 Cache

Content-addressed cache directory for extracted blocks, scripts, chunk audio, and final outputs.

- [ ] Prompt AC: `cache prune --older-than 30d` works
- [ ] Prompt AC: cache key format is versioned
- [ ] Expanded: `cache stats` and `cache clear` exist; prune never touches pinned outputs of the latest manifest
- [ ] Expanded: re-running on an unchanged page completes in under 2 seconds (NFR-004)
- [ ] Expanded: the cache directory is configurable and can live on a persistent volume in server deployments

### FR-021 Doctor

`mr-audio-smith doctor` checks Python version, ffmpeg, GPU and CUDA visibility, backend reachability, model weights presence, LLM provider reachability, registered voices, and disk space.

- [ ] Prompt AC: exit code 0 when all required checks pass
- [ ] Prompt AC: each failure has a fix hint
- [ ] Expanded: checks are classified required or optional per the selected backend; a failed optional check is a warning
- [ ] Expanded: the voice clip quality of every registered voice is re-checked and reported
- [ ] Expanded: a "cloud providers active" warning is printed when any cloud provider is configured
- [ ] Expanded: on Python 3.13 or newer, a Kokoro-related hint recommends Python 3.12
- [ ] Expanded: `--json` output is supported for scripts and CI

### FR-022 Studio review UI

`mr-audio-smith studio` starts a localhost web UI to edit scripts, render and play individual chunks, compare takes, and approve a render.

- [ ] Prompt AC: binds to 127.0.0.1 only by default
- [ ] Prompt AC: no external network calls from the page
- [ ] Expanded: a per-session random token is required on every request; requests without it are rejected
- [ ] Expanded: responses set `Content-Security-Policy: default-src 'self'; media-src 'self' blob:; connect-src 'self'`
- [ ] Expanded: screens: script editor with chunk list, chunk detail with take comparison, render queue, approve and publish panel (see DESIGN.md)
- [ ] Expanded: chunk status is always shown as a text pill, never color alone
- [ ] Expanded: no analytics or telemetry of any kind

### FR-023 HTTP server

`mr-audio-smith serve` exposes a REST API (see ARCHITECTURE) with async jobs.

- [ ] Prompt AC: job status endpoint
- [ ] Prompt AC: artifacts downloadable
- [ ] Prompt AC: optional bearer token auth
- [ ] Expanded: default bind is 127.0.0.1; any other bind requires `AUDIO_SMITH_SERVER_TOKEN` and requests without the token get 401
- [ ] Expanded: CORS is disabled by default with an explicit allowlist when enabled
- [ ] Expanded: job creation is rate limited per token (default 30 per hour)
- [ ] Expanded: artifacts are served only through the API with path validation

### FR-024 MCP server

`mr-audio-smith mcp` exposes MCP tools over stdio and streamable HTTP.

- [ ] Prompt AC: tools listed in Appendix E are present and schema-valid
- [ ] Expanded: `mr_audio_smith_narrate` returns file paths and a duration
- [ ] Expanded: tool errors are structured and never include secrets
- [ ] Expanded: the same security rules (consent, SSRF, path validation) apply as in the CLI

### FR-025 GitHub Action

Composite action `mohnishbasha/mr-audio-smith/action@v1` narrates changed pages in a static-site repo and commits outputs.

- [ ] Prompt AC: runs only for files matching an input glob
- [ ] Prompt AC: supports a self-hosted GPU runner or a remote mr-audio-smith server URL
- [ ] Prompt AC: no-op when hashes are unchanged
- [ ] Expanded: the action commits outputs with a bot identity and skips the commit when nothing changed
- [ ] Expanded: secrets (server token, LLM keys) are read from GitHub secrets and never echoed in logs

### FR-026 Parent track

Content marked data-narrate="parent" is rendered as a separate {slug}.parent.mp3 using the adult-brief profile.

- [ ] Prompt AC: never included in the child track
- [ ] Expanded: the parent track has its own script, chunks, captions, and manifest entry
- [ ] Expanded: when no content is marked parent, no parent track is created
- [ ] Expanded: the embed snippet can expose the parent track as a separate player

---

## 5. Non-functional requirements

Each NFR has a verification method in `docs/TEST_PLAN.md`.

- **NFR-001 Local-first.** With default config, no page text, script, or audio leaves the machine.
- **NFR-002 Zero telemetry.** No analytics, no crash reporting, no update pings.
- **NFR-003 Performance.** A 4-minute-read letter renders end to end in under 3 minutes on a single modern NVIDIA GPU with Maya 2, and under 10 minutes on CPU with Kokoro.
- **NFR-004 Incremental.** Re-running on an unchanged page completes in under 2 seconds.
- **NFR-005 Reliability.** Any single chunk failure does not lose completed chunks.
- **NFR-006 Reproducibility.** Same inputs plus same seeds produce byte-identical scripts (LLM at temperature 0 where supported) and perceptually identical audio.
- **NFR-007 Accessibility.** Player meets WCAG 2.2 AA (keyboard operable, visible focus, 4.5:1 contrast, captions, reduced-motion support, 44px minimum touch targets for children).
- **NFR-008 Portability.** CLI runs on macOS (Apple Silicon), Linux x86_64, Linux arm64 (including NVIDIA Grace-based systems), and Windows via WSL2. Note: the Maya 2 backend itself requires a Linux NVIDIA GPU; other platforms use Kokoro, a remote Maya 2 server, or another backend.
- **NFR-009 Safety.** Voice cloning only from registered voices with consent records.
- **NFR-010 Observability.** Structured JSON logs with `--log-format json`; per-stage timings in the manifest.
- **NFR-011 Player weight.** Web component under 12 KB gzipped, no dependencies.
- **NFR-012 Licensing.** Every runtime dependency and every model weight has a recorded license in THIRD_PARTY_LICENSES.md; non-commercial weights are opt-in and flagged at runtime.

---

## 6. Success metrics

- Flagship: every letter on the reference site has an audio version within 10 minutes of being pushed.
- Listening quality: in a blind A/B, the parent prefers the mr-audio-smith script over a verbatim read in at least 9 of 10 letters.
- Voice similarity: mean speaker-similarity score at least 0.80 across chunks of a cloned voice.
- Incremental builds: at least 95 percent of site-mode runs render zero unchanged pages.

Measurement note: because the product has zero telemetry, these metrics are measured by the maintainers on the reference site and in CI fixtures, not by collecting usage data.

---

## 7. Constraints and assumptions

### Constraints

- Python 3.12 is the reference interpreter. The package supports 3.12; the optional Kokoro extra requires Python below 3.13 upstream and is marked `python_version < "3.13"` (ADR-017).
- ffmpeg 6 or newer must be on PATH for mastering, rate adjustment, and encoding.
- Maya 2 Native requires a Linux host with an NVIDIA GPU (about 8 GB VRAM). Apple MPS is not supported. macOS users use Kokoro or point to a remote Maya 2 server.
- Local-first: defaults must never send content off the machine. Cloud providers are opt-in and flagged by `doctor`.
- Zero telemetry in the CLI, server, Studio, and player.
- Voice cloning requires a consent record; this cannot be disabled by config.
- Player is a dependency-free web component under 12 KB gzipped.
- MIT license; every dependency and model weight license is recorded; non-commercial weights are opt-in.
- Maya 2 server default URL is `http://127.0.0.1:8080/v1`; server requires `speed=1.0`, so speaking rate is applied after synthesis.
- Output is 24 kHz mono from Maya 2, mastered to MP3 128 kbps mono 44.1 kHz by default.

### Assumptions

- The author owns the voice being cloned or holds written permission.
- Source pages are static or server-rendered HTML; pages that require JavaScript to render content are out of scope (HTML is parsed, never executed).
- A local Ollama (or configured LLM provider) is available for the script stage.
- The static-site host can serve MP3, VTT, and a small JS file.
- Executing agents cannot perform GPU-runner Maya 2 integration, human listening tests of cloned voices, PyPI/npm/GHCR publishing, or DNS setup; those are manual steps recorded as skipped or deferred in the test and sprint plans.

---

## 8. Out of scope for v1

Each item gets a GitHub issue with the `enhancement` label.

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

## 9. Glossary

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
| Consent record | Stored name, relationship, date, and statement authorizing a voice to be cloned |
| Lexicon | Word to phonetic respelling map applied only at synthesis time |
| Manifest | JSON file describing one narration run and its outputs |
| Peaks | 28 integers (0 to 100) precomputed in mastering that drive the player waveform |
| Studio | Localhost review UI for editing scripts, comparing takes, and approving renders |
| Sting | Short intro or outro sound added during mastering |

---

## 10. Open questions

1. Should the Maya 2 adapter expose `top_k`, `top_p`, and `repetition_penalty` in profiles, or keep them as backend-level config only?
2. Is the default `takes_per_chunk` of 2 enough to reach the 0.80 mean similarity target, or should the default be 3 on GPU runs?
3. What is the retention default for cached takes (30 days is the prune example; confirm as the default)?
4. Should the GitHub Action support a dry-run mode that comments the diff on a pull request?
5. How should the parent track be exposed in the default embed: a second player, or a tab inside one player?
6. Which license applies to the shipped sting audio, and is it recorded in THIRD_PARTY_LICENSES.md?

---

## 11. Traceability matrix (US to FR)

| User story | Functional requirements |
|---|---|
| US-001 | FR-001, FR-002, FR-004, FR-005, FR-006, FR-009, FR-012, FR-014, FR-016 |
| US-002 | FR-010, FR-011, FR-013 |
| US-003 | FR-005, FR-006, FR-022 |
| US-004 | FR-012, FR-020, FR-022 |
| US-005 | FR-002, FR-026 |
| US-006 | FR-015, FR-017, FR-018 |
| US-007 | FR-008, FR-010, FR-017 |
| US-008 | FR-003, FR-020, FR-025 |
| US-009 | FR-004, FR-005 |
| US-010 | FR-009, FR-010 |
| US-011 | FR-002, FR-005, FR-006, FR-014 |
| US-012 | FR-015, FR-017 |
| US-013 | FR-016, FR-024 |
| US-014 | FR-020, FR-021, FR-023 |
| US-015 | FR-009, FR-010, FR-011 |
| US-016 | FR-003, FR-019, FR-020 |
| US-017 | FR-012, FR-013, FR-022 |
| US-018 | FR-011, FR-021 |

Coverage check: every FR-001 through FR-026 is referenced by at least one story or by a non-functional need. FR-007 (lexicon) and FR-023 are support requirements: FR-007 supports US-001 and US-011 narration quality; FR-023 supports US-014.
