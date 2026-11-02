# mr-audio-smith Architecture

Status: v1 specification. Date: 2026-11-01. Repository: mohnishbasha/mr-audio-smith.

This document is the binding architecture for mr-audio-smith. It records the system shape, the decisions behind it, the module boundaries, every data format and public contract, and the security and deployment model. Where this document and the PRD disagree on a technical matter, this document wins; where they disagree on product behavior, the PRD wins.

Contents:

1. System overview
2. Decision log
3. Package and module map
4. Data flow
5. Data formats
6. Contracts
7. Caching model
8. Error model
9. Security model
10. Deployment topologies and configuration

---

## 1. System overview

mr-audio-smith turns web pages (or local HTML/Markdown files) into narrated audio tracks. It runs a five-stage pipeline: fetch and extract content into typed blocks, write a spoken-word script with an LLM guided by an audience profile, synthesize speech per chunk with a pluggable TTS backend, master the audio with ffmpeg, and publish the result (MP3, WebVTT captions, manifest, embeddable player snippet, optional HTML injection).

The library `audio_smith.api` is the core. The CLI, REST server, MCP server, Studio UI, GitHub Action, and Pi extension are thin front doors over it. Stages are pure functions over typed models and files, so any stage can be re-run alone. A single content-addressed cache sits under the whole pipeline.

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

### 1.1 Stage responsibilities

| Stage | Module | Input | Output | Notes |
|---|---|---|---|---|
| 1 Fetch + extract | `fetch.py`, `extract.py`, `blocks.py` | URL or file path | Block JSON (`{slug}.blocks.json`) | SSRF guard, size and time limits, selectolax DOM walk, trafilatura fallback |
| 2 Script | `script/` | Block JSON + Profile + LLMProvider | Script Markdown (`{slug}.{lang}.script.md`) | Prompt build, validation, optional translation, lexicon |
| 3 Synth | `tts/`, `voices/`, `qa/` | Script Markdown + Voice + TTSBackend | per-chunk PCM/WAV with QA metadata | Per-chunk synthesis, takes, speaker-similarity QA |
| 4 Master | `master/` | chunk WAVs + Profile mastering section | track MP3 per language/kind | Join, pauses, stings, loudnorm, ID3, peaks |
| 5 Publish | `publish/` | tracks + metadata | MP3, VTT, manifest JSON, embed snippet, injected HTML | Manifest validated against `schemas/manifest.schema.json` |

### 1.2 Design principles (from Appendix I of the source prompt)

1. Stages are pure functions over files. Each stage reads typed inputs and writes typed outputs; any stage can be re-run alone.
2. Interfaces are tiny. `TTSBackend` has three methods plus capabilities; `LLMProvider` has two. Adding a backend is one file, one registry entry, and tests.
3. Adapters absorb quirks. Marker handling, voice mapping, and language codes for a model live in its adapter, never in the pipeline.
4. Front doors are thin. CLI, Studio, REST, MCP, Action, and Pi extension call `audio_smith.api` only (enforced by import-linter).
5. Profiles are data. No audience logic in code beyond reading profile fields. New audiences need no release.
6. Caching is a cross-cutting concern with one key module; no stage computes its own ad hoc cache keys.
7. Safety in core. Consent, SSRF guard, path guard, and license guard live below every front door.
8. Optional extras stay optional. The base install has no torch; each backend imports heavy dependencies lazily and reports a clear doctor hint when missing.

---

## 2. Decision log

Each record uses Context / Decision / Consequence. ADR-001 to ADR-014 carry the source prompt's decisions verbatim in the Decision field (with the prompt's "Why" preserved under Context); ADR-015 to ADR-018 were added during specification.

### ADR-001: Core language is Python 3.12, not Rust or TypeScript

- **Context:** Every viable open TTS model (Maya 2 Native, Kokoro, Chatterbox) ships Python inference code on PyTorch; a Rust or TS core would wrap Python anyway. The Serverless Ventures defaults are Tauri, Rust, and a bun-compiled TypeScript CLI, and this product deviates deliberately because its core value lives in Python model runtimes. Rejected alternatives: Rust core (would wrap Python anyway), TypeScript (no model runtimes).
- **Decision:** Core language is Python 3.12, not Rust or TypeScript. Supported range is `>=3.12,<3.14`.
- **Consequence:** Python coding standards replace the Rust standards in the build prompt. The CLI is Python plus typer, installed with `uv tool`, in the same process as the pipeline (no IPC); a bun-compiled TS binary is rejected because it cannot host PyTorch.

### ADR-002: CLI-first, no desktop shell in v1

- **Context:** The flagship user is an engineer automating a static site; the Studio web UI on localhost covers interactive review without a Tauri bundle. Tauri was rejected because it adds a Rust shell and signing for little gain in v1.
- **Decision:** CLI-first, no desktop shell in v1.
- **Consequence:** Zero install friction for the flagship user. Interactive review is served by the Studio UI bound to 127.0.0.1. Rust and Tauri standards from the portfolio template do not apply.

### ADR-003: Default TTS backend is Maya 2 Native (Apache 2.0) via its OpenAI-compatible endpoint

- **Context:** Zero-shot cloning from 3 to 10 s of reference audio, English plus 11 Indian languages with cross-lingual cloning, permissive license, streaming support. Rejected: Maya1 (no cloning), XTTS and F5-TTS (non-commercial weights), ElevenLabs as default (cloud, paid, privacy).
- **Decision:** Default TTS backend is Maya 2 Native (Apache 2.0) via its OpenAI-compatible endpoint.
- **Consequence:** No inline emotion tags; expressiveness is carried by script wording, punctuation, pauses, and rate. Verified API facts and the resulting adapter behavior are recorded in section 6.6. The server's default port is 8080, so the default `AUDIO_SMITH_MAYA2_URL` is `http://127.0.0.1:8080/v1` (the source prompt said 8000; this is a deliberate spec change). Maya 2 needs a Linux NVIDIA GPU (about 8 GB VRAM); there is no Apple MPS path.

### ADR-004: One OpenAI-compatible backend class serves Maya 2 server, OpenAI cloud, and any other compatible server

- **Context:** The Maya 2 server exposes `POST /v1/audio/speech` in the OpenAI shape, as do OpenAI and many local servers. Duplicating HTTP, retry, and response handling per model would multiply bugs.
- **Decision:** One OpenAI-compatible backend class serves Maya 2 server, OpenAI cloud, and any other compatible server; model-specific behavior lives in small adapters.
- **Consequence:** `tts/openai_compat.py` owns transport, retries, and error mapping. `tts/maya2.py` is an adapter (voice registration, language codes, rate handling, in-process mode) rather than a second client.

### ADR-005: Synthesis is per chunk (2 to 4 sentences, max 400 chars default)

- **Context:** Long inputs make TTS drift in timbre and pacing; per-chunk enables caching, retries, QA, and single-paragraph re-render.
- **Decision:** Synthesis is per chunk (2 to 4 sentences, max 400 chars default).
- **Consequence:** The chunk is the unit of caching (`chunk_key`), QA (speaker similarity per take), retry, and partial re-render (`render --chunks 3,7`). Profiles may lower the maximum (`speech.max_chunk_chars`).

### ADR-006: Scripts are stored as human-editable Markdown, separate from audio

- **Context:** The author must be able to review and edit before rendering (US-003, US-004).
- **Decision:** Scripts are stored as human-editable Markdown, separate from audio.
- **Consequence:** A strict, tiny grammar (section 5.2) is parsed and validated; hand edits are first-class, and `content_hash` in the frontmatter detects drift from the source. The `--approve` gate and Studio both operate on this file.

### ADR-007: Content-addressed cache keyed on normalized content plus all inputs that affect output

- **Context:** Re-running a site of 50 pages must cost nothing when nothing changed, and a single edited paragraph must re-synthesize only that chunk.
- **Decision:** Content-addressed cache keyed on normalized content plus all inputs that affect output.
- **Consequence:** One module (`cache/keys.py`) computes every key. Keys include the prompt template version, voice clip hash, seed, and rate (section 7).

### ADR-008: Mastering uses ffmpeg via subprocess with argument arrays (never shell strings); pydub only for in-memory joins

- **Context:** ffmpeg arguments include paths derived from user and URL input; shell strings create injection and quoting risks.
- **Decision:** Mastering uses ffmpeg via subprocess with argument arrays (never shell strings); pydub only for in-memory joins.
- **Consequence:** `master/ffmpeg.py` is the only place that spawns ffmpeg. `ffmpeg>=6.0` with libmp3lame, libopus, and ebur128 is a hard system requirement, verified by `doctor`.

### ADR-009: Player is a dependency-free web component with a native `<audio>` fallback

- **Context:** The player drops into arbitrary static sites; forcing a framework on host pages is unacceptable (React component rejected). Target size is under 12 KB.
- **Decision:** Player is a dependency-free web component with a native `<audio>` fallback.
- **Consequence:** `<audio-smith-player>` is TypeScript compiled to a single file; if custom elements or JS fail, the plain `<audio controls>` still plays. Playback position is the only thing stored (localStorage, in try/catch).

### ADR-010: Voice cloning requires a consent record; enforced in core, not just CLI

- **Context:** Cloned voices carry impersonation risk; a CLI-only check would be bypassed by the REST API, MCP tools, or the Python API.
- **Decision:** Voice cloning requires a consent record; enforced in core, not just CLI.
- **Consequence:** `voices/consent.py` runs below every front door and raises `ConsentError` (exit code 8). Tool descriptions for MCP state that cloning needs a registered voice with consent.

### ADR-011: LLM provider default is Ollama (local); Anthropic and OpenAI-compatible optional

- **Context:** Local-first matches the portfolio default and keeps source text private. Cloud-only was rejected for privacy.
- **Decision:** LLM provider default is Ollama (local); Anthropic and OpenAI-compatible optional.
- **Consequence:** Default model is `ollama:qwen3:14b` (0.6B for CI and dev). Cloud providers activate only when explicitly configured, and `doctor` warns when any are active.

### ADR-012: Server uses FastAPI with an in-process job queue (asyncio + one GPU worker) in v1; Redis-backed queue deferred

- **Context:** Simple, typed, async. Celery plus Redis is deferred.
- **Decision:** Server uses FastAPI with an in-process job queue (asyncio + one GPU worker) in v1; Redis-backed queue deferred.
- **Consequence:** Jobs persist to SQLite (`jobs.db`) so restarts keep history; a single worker serializes GPU use. Horizontal scale-out of workers is out of scope for v1.

### ADR-013: MCP server uses the official Python MCP SDK; harness integrations ride on it

- **Context:** One server covers all MCP harnesses (Claude Code, Goose, OpenCode). The Pi extension is TypeScript and calls the REST server for richer slash commands and streaming progress.
- **Decision:** MCP server uses the official Python MCP SDK; harness integrations ride on it.
- **Consequence:** No per-harness code for MCP harnesses; transports are stdio and streamable HTTP.

### ADR-014: Kokoro is the CPU fallback backend; Chatterbox optional extra; XTTS and F5-TTS are excluded by default because their weights are non-commercial

- **Context:** A CPU path is required for laptops, CI, and users without NVIDIA GPUs. Kokoro-82M is Apache-2.0 and fast on CPU (Piper was rejected for lower naturalness). Chatterbox is MIT and a clone-capable option.
- **Decision:** Kokoro is the CPU fallback backend; Chatterbox optional extra; XTTS and F5-TTS are excluded by default because their weights are non-commercial.
- **Consequence:** `Capabilities.license` and `commercial_ok` let a license guard refuse non-commercial models unless explicitly overridden.

### ADR-015: Speaker similarity uses resemblyzer (qa extra), lazy-imported

- **Context:** Per-take QA compares the speaker embedding of synthesized audio to the reference clip to detect timbre drift. The source prompt left the choice between resemblyzer and speechbrain to a Sprint 3 ADR. resemblyzer is Apache-2.0 and small.
- **Decision:** Speaker similarity uses resemblyzer (the `qa` extra), lazy-imported. When it is absent, similarity checks are skipped and the manifest records a warning.
- **Consequence:** The base install stays torch-free. `doctor` reports a hint to install `mr-audio-smith[qa]`. With `qa.takes_per_chunk` greater than 1 and similarity unavailable, the first take is kept and the chunk's `similarity` field is null.

### ADR-016: Maya 2 speaking rate is applied post-synthesis (ffmpeg atempo)

- **Context:** The Maya 2 server requires `speed` to be exactly 1.0 in `POST /v1/audio/speech`. Profiles define `speech.rate` (for example 0.9 for a five-year-old listener).
- **Decision:** The Maya 2 adapter always sends `speed: 1.0` and applies the profile rate after synthesis with ffmpeg `atempo`.
- **Consequence:** `rate` is part of `chunk_key`, so the cached WAV is the rate-adjusted audio. Rate must stay inside atempo's useful range (profile schema constrains it to 0.5..2.0). Pitch is preserved by atempo; very low rates may introduce slight artifacts and are covered by the listening tests.

### ADR-017: Kokoro requires Python below 3.13 upstream

- **Context:** The project supports Python 3.12 and 3.13, but the Kokoro package does not support 3.13.
- **Decision:** The `kokoro` extra is marked `python_version < "3.13"`. On Python 3.13, `doctor` hints to use Python 3.12 for Kokoro.
- **Consequence:** On 3.13 the CPU fallback is unavailable through the extra; the mock backend and OpenAI-compatible backends still work. CI covers Kokoro on 3.12 only.

### ADR-018: Delivery process is one feature branch and PR per sprint

- **Context:** A single autonomous agent executes the sprint plan; one PR per task would create a long serial chain of reviews with little parallelism benefit.
- **Decision:** One feature branch plus one PR per sprint (`feature/sprint-N-<slug>`), closing all of that sprint's issues. TDD, the spec protocol, and implementation comments still apply per issue.
- **Consequence:** PR descriptions list every closed issue (`Closes #n`). Commits remain issue-scoped so history stays reviewable. Things the executing agent cannot do (GPU runner integration, human listening tests, publishing to PyPI/npm/GHCR, DNS) are marked Skipped or Deferred with a manual step in the plans.

---

## 3. Package and module map

```
audio_smith/
  __init__.py          version via importlib.metadata
  cli.py               typer app: run, script, render, inject, site, voice, profile,
                       doctor, studio, serve, mcp, cache
  config.py            pydantic-settings; env prefix AUDIO_SMITH_
  errors.py            AudioSmithError hierarchy (code, stage, message, hint)
  proc.py              the only subprocess entry point: argument arrays, no shell, timeouts
  paths.py             safe_slug, ensure_inside (output root guard), atomic_write
  preflight.py         PreflightIssue model shared by backends, LLM providers, doctor
  cli_commands.py      stage commands registered on the typer app (front door)
  pipeline.py          stages 3 to 5 for one track (plan, synth, QA, assemble, master, VTT, track cache)
  orchestrate.py       narrate(): the whole pipeline for one page, exposed as api.narrate
  pipeline_types.py    models passed between synthesis, mastering, and publish
  script/verbatim.py   splices exact verbatim text and the signature into LLM output
  api.py               the core public API: narrate, extract, write_script,
                       render_script, master, publish (only module front doors import)
  fetch.py             httpx fetch, size/time limits, scheme allowlist, SSRF guard
  extract.py           selectolax (lexbor backend) DOM walk -> Block list; trafilatura and
                       text-density fallbacks; local .md converted to HTML in api.py
  blocks.py            Block model, normalization, hashing
  profiles/            loader.py, schema.py, builtin/{kid-5,kid-8,adult-commute,adult-brief}.yaml
  script/              writer.py (LLM prompt build), validate.py, translate.py,
                       markdown.py (Script Markdown parse/serialize), lexicon.py,
                       prompts/{writer.md,translate.md}
  llm/                 base.py (LLMProvider), ollama.py, anthropic.py, openai_compat.py, fake.py
  tts/                 base.py (TTSBackend, Capabilities), maya2.py, kokoro.py,
                       chatterbox.py, openai_compat.py, mock.py, registry.py
  voices/              registry.py, consent.py, clipcheck.py
  qa/                  similarity.py (speaker embeddings), loudness.py
  master/              assemble.py, ffmpeg.py, stings.py, tags.py, peaks.py
  publish/             manifest.py, vtt.py, embed.py, inject.py
  cache/               store.py, keys.py
  site.py              index crawl + batch
  server/              app.py (FastAPI), jobs.py, auth.py, models.py
  mcp_server/          server.py, tools.py
  studio/              routes.py, static/ (built from web/studio)
  doctor.py
schemas/               blocks, script, profile, manifest, voice  (*.schema.json)
player/                TypeScript web component <audio-smith-player>
web/studio/            Studio UI (TypeScript + Vite, no framework or Preact)
integrations/pi/       @mr-audio-smith/pi-extension (TypeScript)
integrations/goose/    toolkit.yaml
integrations/opencode/ config snippet
integrations/claude-code/  README.md, skill/SKILL.md
action/                composite GitHub Action (action.yml, narrate-changed.py)
```

### 3.1 Additions beyond the original module map

| Module | Purpose |
|---|---|
| `errors.py` | Single home of the typed error hierarchy so every front door maps errors identically (section 8). |
| `api.py` | The library-first core surface. Pure orchestration over stages; the only internal module front doors may import besides models. |
| `master/peaks.py` | Computes per-track waveform peaks (downsampled amplitude array) for the player's waveform and the manifest. |
| `tts/chatterbox.py` | Optional Chatterbox backend (MIT, GPU recommended), behind the `chatterbox` extra. |
| `script/prompts/` | Versioned prompt templates (`writer.md`, `translate.md`). The template version feeds `script_key`. |
| `schemas/` | JSON Schemas for blocks, script frontmatter, profile, manifest, voice, generated from the pydantic models and checked in CI. |

### 3.2 Dependency rule (import-linter)

Front-door modules (`cli`, `server`, `mcp_server`, `studio`, and the action/Pi integrations that call them) may import only `audio_smith.api` and shared model modules (`audio_smith.errors`, `audio_smith.config`, and pydantic model modules). They must not import stage modules (`fetch`, `extract`, `script.*`, `tts.*`, `master.*`, `publish.*`, `voices.*`, `qa.*`, `cache.*`) directly. This is enforced in CI by an `import-linter` `forbidden` contract. There is no separate "core extraction" sprint because the project is library-first from Sprint 1.

Layering, top to bottom: front doors, `api`, stages (`fetch/extract`, `script`, `tts`, `master`, `publish`), cross-cutting (`cache`, `voices`, `qa`, `config`, `errors`). Cross-cutting modules never import stages.

### 3.3 Optional dependencies

| Extra | Contents | Notes |
|---|---|---|
| (base) | typer, rich, httpx, selectolax, trafilatura, emoji, pydantic, pydantic-settings, pyyaml, structlog, numpy, soundfile, pydub, mutagen, openai, keyring | No torch |
| `maya2` | `torch` | In-process Maya 2 Native. `maya3` is not on PyPI (PyPI forbids direct URL dependencies); install it with `uv pip install "maya3 @ git+https://github.com/MayaResearch/maya2-native@<pinned sha>"` |
| `kokoro` | `kokoro>=0.9`, `torch>=2.4` | Marked `python_version < "3.13"` (ADR-017) |
| `chatterbox` | `chatterbox-tts`, `torch>=2.4` | Optional clone backend |
| `qa` | `resemblyzer>=0.1.4` | ADR-015 |
| `cloud` | `anthropic>=0.34` | Anthropic LLM provider |
| `server` | `fastapi>=0.112`, `uvicorn[standard]>=0.30` | REST and Studio |
| `mcp` | `mcp>=1.2` | MCP server |

---

## 4. Data flow

### 4.1 `run`

`mr-audio-smith run <url|file>` (also `api.narrate`).

1. Load configuration (flags, env, `audio-smith.toml`, defaults) and resolve the profile, voice, backend, LLM, and languages.
2. Preflight: `TTSBackend.preflight()`, `LLMProvider.preflight()`, ffmpeg presence, voice consent. Any blocking issue raises `PreflightError` (exit 3) before any work is done.
3. Fetch the source (scheme allowlist, SSRF guard, size and time limits, pinned IP), or read the local file. Failures raise `FetchError` (exit 4).
4. Extract to a Block list (selectolax DOM walk, trafilatura fallback); normalize and compute `content_hash`; write `{slug}.blocks.json` and cache it under `blocks/{content_hash}.json`. Empty or unusable results raise `ExtractError` (exit 4).
5. For each requested language and each track kind (`main`, plus `parent` if the profile defines `tracks.parent`): look up `script_key` in the cache; on a miss, build the prompt from blocks, profile, and lexicon, call the `LLMProvider`, parse and validate the output as Script Markdown, translate when `lang` differs from the source language, and write `{slug}.{lang}.script.md`. Invalid output is retried up to the configured limit, then raises `ScriptInvalidError` (exit 5).
6. If `--dry-run`, print the plan (chunks, estimated minutes, cache hits) and stop. If the approval gate applies (default unless `--approve`), stop after the script and report the script path for review.
7. Synthesize each chunk: apply the lexicon, compute `chunk_key`, reuse a cached WAV when present; otherwise call `TTSBackend.synth` for `qa.takes_per_chunk` takes (distinct seeds), score each take by speaker similarity (when available), keep the best, and cache it. Takes below `qa.threshold` produce manifest warnings (and a retry when takes remain). Persistent failures raise `SynthesisError` (exit 6).
8. Master each track: join chunks with the profile's `pause_between_chunks_ms` and `pause_after_heading_ms` plus inline `[pause N]` markers, add intro/outro stings and an optional ducked music bed, apply EBU R128 loudness normalization (`loudnorm`), write ID3 tags, encode MP3, compute peaks. Cache under `tracks/{track_key}.mp3`. Failures raise `MasteringError` (exit 7).
9. Publish: write VTT captions from chunk durations, build the manifest (validated against `schemas/manifest.schema.json`), render the embed snippet, and, when `--inject page.html` is given, insert the player into the HTML at the selector. Write outputs under the output root (path-guarded).
10. Return a result (manifest path, tracks, warnings). The CLI prints a summary and exits 0.

`script`, `render`, and `inject` are slices of this flow: `script` runs steps 1 to 5 and stops; `render` runs steps 7 to 9 from an existing script (optionally a subset of chunks); `inject` runs only the injection part of step 9 from a manifest.

### 4.2 `site`

`mr-audio-smith site <index-url> --match "letter-*.html" [--max-pages 50] [run flags]` (also `site.py`).

1. Fetch the index page (same guards as `fetch`).
2. Collect links, resolve against the index URL, and keep only same-origin links that match the glob; cap at `--max-pages`.
3. De-duplicate and order the page list deterministically.
4. For each page, run the `run` flow (steps 1 to 10 above) with shared configuration; the shared cache makes unchanged pages near-free.
5. Continue past per-page failures, collecting them as per-page errors and manifest warnings; do not abort the batch.
6. Write a batch summary (pages processed, cache hits, failures, total audio minutes). The exit code is 0 if all pages succeeded, otherwise the highest-severity error's exit code.

### 4.3 `serve`

`mr-audio-smith serve [--host 127.0.0.1] [--port 7340]` (FastAPI app in `server/`).

1. Load configuration; refuse to start on a non-loopback bind without `AUDIO_SMITH_SERVER_TOKEN` (`UsageError`, exit 2).
2. Open (or create) `jobs.db` in SQLite; mark any jobs left `running` by a previous process as `failed` with a restart note (or re-queue, per config).
3. Start the single GPU worker consuming an asyncio queue.
4. `POST /v1/jobs` validates the body, applies auth and the per-token rate limit, persists a `queued` job, enqueues it, and returns `202 {job_id}`.
5. The worker pops a job, calls `api.narrate` with a progress callback, and writes `status`, `stage`, and `progress` (per stage and chunk) to SQLite. Artifacts go to `OUT_DIR/jobs/{id}`.
6. Clients poll `GET /v1/jobs/{id}`, then fetch `/manifest` and `/files/{name}`. File names are validated against the job's artifact list (path guard).
7. Errors are converted to RFC 9457 problem+json. `/healthz` reports liveness; `/readyz` reports backend reachable and model loaded plus ffmpeg present.
8. Remote mode: the CLI's `--server URL --token ...` submits the same job through this API and downloads the artifacts.

### 4.4 `mcp`

`mr-audio-smith mcp [--transport stdio|http]` (`mcp_server/`).

1. Start the official Python MCP SDK server on stdio (default) or streamable HTTP. HTTP transport applies the same bearer-token rule as the REST server on non-loopback binds.
2. Register the 8 tools (section 6.4) with JSON Schemas generated from pydantic input and output models.
3. On `tools/call`, validate input, then call the matching `audio_smith.api` function.
4. For long-running `narrate`, emit MCP progress notifications per stage.
5. Map `AudioSmithError` to an MCP tool error carrying `code`, `stage`, `message`, and `hint` (no stack traces).
6. Return absolute file paths in results so agents can open the outputs directly.

---

## 5. Data formats

All persisted formats carry a `schema` id with a major version (`audio-smith/<name>@<n>`). JSON Schemas for each are published under `schemas/`.

### 5.1 Block JSON

File: `{slug}.blocks.json`. Schema id `audio-smith/blocks@1`.

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

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema` | string | yes | Constant `audio-smith/blocks@1` |
| `source` | string | yes | URL or file path of origin |
| `title` | string | yes | Document title |
| `lang` | string | yes | BCP-47 primary subtag of the source language (for example `en`) |
| `blocks[].id` | string | yes | `bNNN`, unique and stable within the document |
| `blocks[].type` | enum | yes | `title`, `heading`, `paragraph`, `list_item`, `quote`, `signature` |
| `blocks[].text` | string | yes | Normalized text (whitespace collapsed, emoji handled) |
| `blocks[].track` | enum | yes | `main` or `parent` (adult side-content track) |
| `blocks[].index` | int | no | List position for `list_item` |
| `blocks[].heading` | string | no | Owning heading for `list_item` |
| `blocks[].verbatim` | bool | no | Default false; true means the LLM must not change the text |

### 5.2 Script Markdown

File: `{slug}.{lang}.script.md`. Schema id `audio-smith/script@1`.

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

**Grammar rules** (enforced by `script/validate.py`; anything else is a validation error):

1. The file starts with a YAML frontmatter block delimited by `---` lines. Required keys: `schema` (must be `audio-smith/script@1`), `source`, `profile` (form `id@version`), `lang`, `content_hash`, `generated_by` (form `provider/model`). Unknown keys are rejected. Hand-written scripts may set `generated_by: human`.
2. After the frontmatter, the body is a sequence of chunks. A chunk begins with a heading line matching `^## (\d{3,})( \{verbatim\})?$`: two hashes, a space, a zero-padded number of at least three digits, and optionally a single space followed by `{verbatim}`.
3. Chunk numbers start at 001, are strictly increasing, and have no gaps.
4. Chunk text is one or more lines of plain text following the heading, up to the next `## ` heading or end of file. Blank lines inside a chunk are allowed and collapse to a single break.
5. A `{verbatim}` chunk must match the source block text it corresponds to (normalized for whitespace and terminal punctuation); the validator rejects LLM rewrites of verbatim chunks.
6. The only inline markers are `[pause N]` and `*word*`.
   - `[pause N]`: N is an integer number of milliseconds from 100 to 3000 inclusive. Written exactly as `[pause ` followed by digits and `]`. A pause marker may appear mid-line or at the end of a line.
   - `*word*`: a single word wrapped in single asterisks, meaning gentle emphasis. One word only (no spaces inside). Backend adapters render it or ignore it.
7. No other Markdown is allowed in chunk text: no lists, links, images, code, tables, HTML, additional heading levels, or double-asterisk bold. No SSML or emotion tags such as `[laugh]`.
8. Each chunk's text, after removing markers, must not exceed the effective `max_chunk_chars` (profile value, capped by the backend capability) and should hold 2 to 4 sentences. Over-length chunks are a validation error; sentence count outside the range is a warning.
9. Lexicon substitution (`profile.lexicon`) is applied at synthesis time, not written into the script.

### 5.3 Profile YAML

File: `profiles/<id>.yaml` (built-ins in `audio_smith/profiles/builtin/`). Schema id: `audio-smith/profile@1` (the `schema` key is optional in the file and implied). Built-in profiles: `kid-5`, `kid-8`, `adult-commute`, `adult-brief`.

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

**Field table**

| Path | Type | Default | Constraints |
|---|---|---|---|
| `id` | string | required | `^[a-z0-9][a-z0-9-]{0,39}$`; unique among loaded profiles |
| `version` | string | required | Semantic version `MAJOR.MINOR.PATCH` |
| `description` | string | `""` | Max 200 chars |
| `audience.age` | int | null | 3..99 when set |
| `audience.attention_minutes` | number | null | greater than 0; script longer than this yields a warning |
| `writing.target_minutes` | number | 5 | 0.5..60 |
| `writing.max_sentence_words` | int | 20 | 4..60 |
| `writing.explain_big_words` | bool | false | |
| `writing.spoken_transitions` | bool | false | Adds spoken signposting ("Idea number two") |
| `writing.interactive_moments` | int | 0 | 0..10 |
| `writing.keep_signature_verbatim` | bool | true | Signature blocks become `{verbatim}` chunks |
| `writing.forbidden` | list of string | `[]` | Free-form tags passed to the writer prompt |
| `writing.parent_headings` | list of string | omitted (optional) | Heading texts routed to the `parent` track; when omitted, track assignment comes from extraction |
| `speech.rate` | number | 1.0 | 0.5..2.0; applied by the backend or post-synthesis (ADR-016) |
| `speech.pause_after_heading_ms` | int | 600 | 0..3000 |
| `speech.pause_between_chunks_ms` | int | 300 | 0..3000 |
| `speech.max_chunk_chars` | int | 400 | 80..400 (capped by backend `max_chars`) |
| `languages` | list of string | `[en]` | Non-empty; each a supported language code; one track per language |
| `tracks` | map kind to profile id | `{}` | Only key in v1: `parent`; value must reference an existing profile id |
| `mastering.intro_sting` | string or null | null | `builtin:<name>` or a file path inside the project |
| `mastering.outro_sting` | string or null | null | Same form |
| `mastering.music_bed` | string or null | null | `builtin:<name>` or path; ducked under voice |
| `lexicon` | map string to string | `{}` | Key: written form, value: respelling; keys case-sensitive; max 500 entries |
| `qa.takes_per_chunk` | int | 2 | 1..5; takes synthesized per chunk, best kept |
| `qa.threshold` | number | 0.75 | 0.0..1.0; minimum speaker similarity; overridden by `AUDIO_SMITH_QA_THRESHOLD` |

Unknown keys are validation errors in profiles (`mr-audio-smith profile validate <file>`), so typos do not silently change behavior.

### 5.4 Manifest JSON

File: `{slug}.manifest.json`. Schema id `audio-smith/manifest@1`. JSON Schema published at `schemas/manifest.schema.json`. Manifests never contain secrets, reference clips, or consent statements (voice id only).

| Field | Type | Notes |
|---|---|---|
| `schema` | string | Constant `audio-smith/manifest@1` |
| `tool_version` | string | mr-audio-smith version |
| `source` | string | URL or file path |
| `title` | string | |
| `profile` | object | `{id, version}` |
| `backend` | object | `{id, model}` |
| `llm` | string | Provider string used for scripting (no keys) |
| `voice_id` | string | Voice id only |
| `content_hash` | string | Hash of normalized source content |
| `created_at` | string | RFC 3339 UTC timestamp |
| `approved` | bool | True when the script passed the approval gate (`--approve` or Studio approval) |
| `tracks[]` | array | One per language and kind |
| `tracks[].lang` | string | Language code |
| `tracks[].kind` | enum | `main` or `parent` |
| `tracks[].file` | string | Relative path to the MP3 |
| `tracks[].duration_s` | number | |
| `tracks[].loudness_lufs` | number | Integrated loudness |
| `tracks[].true_peak_dbtp` | number | |
| `tracks[].peaks` | array of number | Downsampled waveform peaks, each 0.0..1.0 (from `master/peaks.py`) |
| `tracks[].captions` | string | Relative path to the WebVTT file for this track |
| `tracks[].opus` | string, optional | Relative path to the Opus file when `--opus` was requested |
| `chunks[]` | array | One per rendered chunk |
| `chunks[].id` | string | Chunk number (for example `001`) |
| `chunks[].hash` | string | `chunk_key` |
| `chunks[].take` | int | Index of the kept take |
| `chunks[].seed` | int | Seed of the kept take |
| `chunks[].similarity` | number or null | Speaker similarity; null when QA unavailable |
| `chunks[].duration_ms` | int | |
| `timings` | object | Stage name to seconds: `fetch`, `extract`, `script`, `synth`, `master`, `publish` |
| `warnings` | array of string | Human-readable warnings (low similarity, QA skipped, over-length script, and so on) |

### 5.5 Voice record

Layout on disk (directory `0700`, files `0600`):

```
voices/dad/
  voice.yaml          0600
  reference.wav       0600   original consented clip
  reference.24k.wav   0600   resampled 24 kHz mono copy used for synthesis and QA
```

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
clip_hash: 3b1f...a7            # SHA-256 of reference.wav bytes
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | `^[a-z0-9][a-z0-9-]{0,39}$`; equals the directory name |
| `display_name` | string | |
| `backend_hints` | list of string | Backends this voice is expected to work with |
| `reference` | string | File name of the original clip inside the voice directory |
| `reference_text` | string | Transcript of the clip; required for Maya 2 `icl` and `icl_spk` cloning modes |
| `consent.speaker_name` | string | Required |
| `consent.relationship` | enum | `self` or `written_permission` |
| `consent.statement` | string | Required, non-empty |
| `consent.date` | date | Required |
| `clipcheck.*` | numbers | Results of `voices/clipcheck.py` (duration 3..10 s recommended, 24 kHz, SNR, clipping) |
| `clip_hash` | string | SHA-256 of the reference clip; part of `chunk_key` |

`voices/registry.py` creates the directory with `0700` and writes files with `0600`, and refuses to load a voice whose permissions are broader (warning, fixed on request). A voice without a complete consent record cannot be used for synthesis (`ConsentError`).

---

## 6. Contracts

### 6.1 CLI

Binary: `mr-audio-smith` (typer). Global options on every command: `--debug` (show stack traces), `--log-level`, `--config PATH`, `--version`, `--help`.

| Command | Synopsis | Notes |
|---|---|---|
| `run` | `run <url\|file> [--profile kid-5] [--voice dad] [--backend maya2] [--lang en,hi] [--out ./audio] [--inject page.html] [--llm ollama:qwen3:14b] [--approve] [--force] [--dry-run]` | Full pipeline |
| `script` | `script <url\|file> [--profile] [--out]` | Stages 1 to 2 only |
| `render` | `render <script.md> [--chunks 3,7] [--voice] [--backend] [--out]` | Stages 3 to 5 from a script |
| `inject` | `inject <page.html> --manifest <file> [--selector "h1"] [--dry-run]` | Insert the player into HTML |
| `site` | `site <index-url> --match "letter-*.html" [--max-pages 50] [run flags]` | Batch over an index |
| `voice add` | `voice add <id> --clip <wav> --name <speaker> --relationship self` | Also `--statement`, `--reference-text`, `--date`; records consent |
| `voice list` / `check <id>` / `remove <id>` | | `check` re-runs clip checks and permissions audit |
| `profile list` / `show <id>` / `validate <file>` | | |
| `doctor` | `doctor [--json]` | Environment and dependency report |
| `studio` | `studio [--port 7341]` | Always binds 127.0.0.1 |
| `serve` | `serve [--host 127.0.0.1] [--port 7340]` | REST server |
| `mcp` | `mcp [--transport stdio\|http]` | MCP server |
| `cache info` / `prune --older-than 30d` | | |

**Default values and flag semantics**

| Flag | Default | Meaning |
|---|---|---|
| `--profile` | `AUDIO_SMITH_DEFAULT_PROFILE`, else `kid-5` (the flagship listener) | Profile id (optionally `id@version`) |
| `--voice` | config `voice`, else backend default voice | Registered voice id or backend built-in voice |
| `--backend` | `AUDIO_SMITH_DEFAULT_BACKEND` (`maya2`; `mock` in dev) | Backend id |
| `--lang` | profile `languages` | Comma-separated language codes |
| `--out` | `AUDIO_SMITH_OUT_DIR` (`./audio` in prod) | Output root; all writes are path-guarded to it |
| `--inject` | none | HTML file to modify (backup written as `.bak` unless `--force`) |
| `--llm` | `AUDIO_SMITH_LLM` (`ollama:qwen3:14b`) | Provider string (section 6.7) |
| `--approve` | false | Skip the review gate; sets `approved: true` in the manifest |
| `--force` | false | Ignore cache hits and overwrite existing outputs |
| `--dry-run` | false | Print the plan, write nothing |
| `--max-pages` | 50 | Site crawl cap |
| `--selector` | `h1` | CSS selector after which the player is inserted |
| `--server URL`, `--token` | none | Remote mode: submit to a running server |
| `--allow-private` | `AUDIO_SMITH_ALLOW_PRIVATE` | Disable the SSRF private-range block |
| `--port` (studio) | 7341 | |
| `--port` (serve) | 7340 | |
| `--host` (serve) | 127.0.0.1 | Non-loopback requires token |
| `--transport` (mcp) | `stdio` | `stdio` or `http` |


**Exit codes**

| Code | Name | Meaning |
|---|---|---|
| 0 | ok | Success (including `--dry-run`) |
| 2 | usage | Bad arguments, invalid configuration, unsafe server bind |
| 3 | preflight failed | Backend, LLM, or ffmpeg unavailable or misconfigured |
| 4 | extract failed | Fetch or extraction failed (`FetchError`, `ExtractError`) |
| 5 | script invalid | Script failed validation after retries |
| 6 | synthesis failed | TTS failure after retries |
| 7 | mastering failed | ffmpeg or tagging failure |
| 8 | consent missing | Voice lacks a valid consent record |

Exit code 1 is reserved for unexpected internal errors (bugs); these print a short message and, with `--debug`, a stack trace.

### 6.2 Python API

Module `audio_smith.api`. All functions accept an optional `config: Settings | None`, resolve defaults from configuration, and raise `AudioSmithError` subclasses. Progress is reported through an optional `progress: Callable[[ProgressEvent], None]` callback.

```python
from pathlib import Path
from typing import Callable


def narrate(
    source: str | Path,
    *,
    profile: str | None = None,
    voice: str | None = None,
    backend: str | None = None,
    langs: list[str] | None = None,
    llm: str | None = None,
    out_dir: Path | None = None,
    inject_path: Path | None = None,
    approve: bool = False,
    force: bool = False,
    dry_run: bool = False,
    config: "Settings | None" = None,
    progress: Callable[["ProgressEvent"], None] | None = None,
) -> "NarrateResult":
    ...
    # full pipeline; NarrateResult: manifest_path, manifest, tracks, warnings, plan (dry run)


def extract(
    source: str | Path,
    *,
    out_dir: Path | None = None,
    allow_private: bool = False,
    config: "Settings | None" = None,
) -> "BlockDocument":
    ...
    # stage 1; writes {slug}.blocks.json


def write_script(
    blocks: "BlockDocument | Path",
    *,
    profile: str | None = None,
    lang: str | None = None,
    llm: str | None = None,
    out_dir: Path | None = None,
    force: bool = False,
    config: "Settings | None" = None,
) -> "ScriptDocument":
    ...
    # stage 2; writes {slug}.{lang}.script.md


def render_script(
    script: "ScriptDocument | Path",
    *,
    chunks: list[int] | None = None,
    voice: str | None = None,
    backend: str | None = None,
    out_dir: Path | None = None,
    force: bool = False,
    config: "Settings | None" = None,
    progress: Callable[["ProgressEvent"], None] | None = None,
) -> "RenderResult":
    ...
    # stage 3 (and QA); RenderResult: chunk_paths, chunk_records, warnings


def master(
    render: "RenderResult",
    *,
    profile: str | None = None,
    out_dir: Path | None = None,
    config: "Settings | None" = None,
) -> "list[TrackFile]":
    ...
    # stage 4; TrackFile: lang, kind, path, duration_s, loudness_lufs, true_peak_dbtp, peaks


def publish(
    tracks: "list[TrackFile]",
    *,
    blocks: "BlockDocument",
    script: "ScriptDocument",
    inject_path: Path | None = None,
    selector: str = "h1",
    approved: bool = False,
    out_dir: Path | None = None,
    config: "Settings | None" = None,
) -> "Manifest":
    ...
    # stage 5; writes mp3 refs, VTT, manifest, embed snippet, optional HTML injection
```

Also exported from `audio_smith.api` for front doors: `list_voices()`, `list_profiles()`, `list_backends()`, `doctor()`, `recommend()`, `add_voice(...)`, `inject(...)`, `cache_info()`, `cache_prune(older_than)`. Every function is synchronous; the server runs them in a worker thread. All model types are pydantic v2 models exported from `audio_smith.api` so front doors need no other imports.

### 6.3 REST API

FastAPI, prefix `/v1`. JSON bodies unless stated. All endpoints except `/healthz` and `/readyz` require `Authorization: Bearer <token>` when a token is configured (mandatory on non-loopback binds). Errors use RFC 9457 `application/problem+json`:

```json
{
  "type": "https://getaudiosmith.com/problems/script-invalid",
  "title": "Script invalid",
  "status": 422,
  "detail": "Chunk 004 exceeds max_chunk_chars (412 > 360).",
  "code": "script_invalid",
  "stage": "script",
  "hint": "Edit the script or lower writing.max_sentence_words in the profile.",
  "instance": "/v1/jobs/j_01H..."
}
```

| Method and path | Request | Response |
|---|---|---|
| `POST /v1/jobs` | `{"source": str, "profile": str?, "voice": str?, "backend": str?, "langs": [str]?, "options": {"llm": str?, "approve": bool?, "force": bool?, "inject_html": str?, "selector": str?}}` | `202 {"job_id": str}` with `Location: /v1/jobs/{id}` |
| `GET /v1/jobs/{id}` | none | `{"job_id": str, "status": "queued\|running\|done\|failed", "stage": "fetch\|script\|synth\|master\|publish\|null", "progress": {"stage_pct": number, "chunk": int?, "chunks_total": int?}, "created_at": str, "error": problem-object\|null}` |
| `GET /v1/jobs/{id}/manifest` | none | Manifest JSON (section 5.4); 404 until the job is `done` |
| `GET /v1/jobs/{id}/files/{name}` | none | Binary stream (MP3), VTT, or embed snippet; content type by extension |
| `POST /v1/scripts` | `{"source": str, "profile": str?, "lang": str?, "llm": str?}` | `200 {"script_markdown": str, "chunks": int, "est_minutes": number, "content_hash": str}` |
| `POST /v1/render` | `{"script_markdown": str, "chunks": [int]?, "voice": str?, "backend": str?}` | `202 {"job_id": str}` |
| `GET /v1/voices` | none | `[{"id", "display_name", "backends", "cloned"}]` |
| `GET /v1/profiles` | none | `[{"id", "version", "description"}]` |
| `GET /v1/backends` | none | `[{"id", "available", "languages", "cloning", "license"}]` |
| `GET /healthz` | none | `200 {"status": "ok"}` (liveness) |
| `GET /readyz` | none | `200 {"status": "ready", "checks": {"backend": "ok", "model": "loaded", "ffmpeg": "ok"}}` or `503` problem+json naming the failed check |

Status mapping: `UsageError` 400/422, auth failure 401, unknown id 404, rate limit 429 (with `Retry-After`), `PreflightError` 503, `ExtractError`/`FetchError` 422, `ScriptInvalidError` 422, `SynthesisError` 502, `MasteringError` 500, `ConsentError` 403. A failed job reports its problem object in `error` while the HTTP status of `GET /v1/jobs/{id}` stays 200.

### 6.4 MCP tools

Eight tools (Appendix E of the source prompt). Descriptions state that cloning requires a registered voice with consent, so agents do not try to bypass it. File paths returned are absolute. Input schemas below are JSON-Schema-style summaries; `?` marks optional.

| Tool | Input | Output |
|---|---|---|
| `mr_audio_smith_narrate` | `{source: string, profile?: string, voice?: string, backend?: string, langs?: string[], inject_path?: string}` | `{manifest_path: string, tracks: [{lang: string, file: string, duration_s: number}], warnings: string[]}` |
| `mr_audio_smith_script` | `{source: string, profile?: string}` | `{script_path: string, chunks: integer, est_minutes: number}` |
| `mr_audio_smith_render` | `{script_path: string, chunks?: integer[], voice?: string, backend?: string}` | `{files: string[]}` |
| `mr_audio_smith_list_voices` | `{}` | `[{id: string, display_name: string, backends: string[], cloned: boolean}]` |
| `mr_audio_smith_list_profiles` | `{}` | `[{id: string, version: string, description: string}]` |
| `mr_audio_smith_list_backends` | `{}` | `[{id: string, available: boolean, languages: string[], cloning: boolean, license: string}]` |
| `mr_audio_smith_status` | `{}` | Doctor report as JSON (`{ok: boolean, checks: [{name, status, detail, hint?}], cloud_providers_active: boolean}`) |
| `mr_audio_smith_recommend` | `{source?: string, description?: string}` (at least one required) | `{profile: string, backend: string, reason: string}` |

`mr_audio_smith_narrate` is long-running and emits progress notifications per stage (`fetch`, `script`, `synth`, `master`, `publish`). Errors are returned as MCP tool errors with `code`, `stage`, `message`, and `hint`.

### 6.5 TTSBackend and LLMProvider protocols

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

```python
class LLMProvider(Protocol):
    id: str

    def preflight(self) -> list[PreflightIssue]: ...
    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str: ...
```

Supporting models (pydantic v2):

```python
class PreflightIssue(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str  # stable id, e.g. "maya2.unreachable"
    message: str
    hint: str | None = None  # actionable next step


class VoiceRef(BaseModel):
    id: str  # registered voice id, or backend built-in voice name
    builtin: bool = False  # true when id names a backend built-in voice
    reference_wav: Path | None = None  # reference.24k.wav for cloned voices
    reference_text: str | None = None
    clip_hash: str | None = None  # SHA-256 of the original clip
    lang: str = "en"


class SynthParams(BaseModel):
    lang: str = "en"
    rate: float = 1.0  # 0.5..2.0; adapter applies (Maya 2: post-synthesis atempo)
    seed: int | None = None  # same seed + text + voice => same audio where supported
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repetition_penalty: float | None = None
    normalize: bool = True


class PcmAudio(BaseModel):
    samples: "np.ndarray"  # float32 mono, range -1.0..1.0 (arbitrary_types_allowed)
    sample_rate: int  # 24000 for Maya 2 and Kokoro

    @property
    def duration_s(self) -> float: ...
```

Contract rules:

- `synth` is stateless from the pipeline's point of view; any voice registration the backend needs (for example Maya 2 `POST /v1/voices`) is performed lazily and idempotently inside the adapter.
- `synth` raises `SynthesisError` for non-retryable failures; transient failures (503, timeouts) are retried by the transport layer with backoff before surfacing.
- `preflight` never raises; it returns issues. Any `error` severity makes `PreflightError` for the run.
- Inline markers are removed from `text` by the pipeline before `synth` (pauses are assembled at mastering); the adapter receives plain text, with `*word*` emphasis either converted or stripped according to the backend's capability.
- Rate: backends with native speed (Kokoro) apply it directly; Maya 2 and Chatterbox apply it after synthesis with `tts/rate.py` `apply_rate` (ffmpeg `atempo` through `proc.run`).
- Retries: `OpenAICompatBackend` retries 429, 5xx, timeouts, and connection errors twice with exponential backoff and jitter, honoring `retry-after` (capped at 30 s); other 4xx raise `SynthesisError` immediately.
- Consent: cloning backends call `voices.consent.require_consent(voice)` right before cloning; it re-reads `voice.yaml` and re-hashes the clip, so a hand-built `VoiceRef` cannot bypass consent.
- Registry (`tts/registry.py`) maps backend ids (`maya2`, `kokoro`, `chatterbox`, `openai`, `openai_compat`, `mock`) to factories; heavy imports occur inside the factory.

### 6.6 Maya 2 adapter (verified facts)

Source: github.com/MayaResearch/maya2-native (`maya3/client.py`, `maya3/server.py`), verified 2026-11-01.

**Server**

- Start: `python -m maya3.server --ckpt maya-research/maya2-native --host 127.0.0.1 --port 8080 --max-seats N`.
- Default port 8080. This differs from the source prompt (8000); `AUDIO_SMITH_MAYA2_URL` defaults to `http://127.0.0.1:8080/v1`, and compose and Helm probes use port 8080.
- `GET /health`: 503 while loading, 200 when ready. Used by `doctor`, `/readyz`, and container health checks.
- Hardware: Linux with an NVIDIA GPU (about 8 GB VRAM). No Apple MPS.

**Speech endpoint**: `POST /v1/audio/speech`

```json
{
  "model": "maya3",
  "input": "text",
  "voice": "as-dad-3b1f9a7c",
  "language": "en",
  "response_format": "wav",
  "normalize": true,
  "seed": 1234,
  "temperature": 0.7,
  "top_k": 50,
  "top_p": 0.95,
  "repetition_penalty": 1.1,
  "speed": 1.0
}
```

- `response_format`: one of `wav`, `pcm`, `mp3`, `opus`, `flac`. The adapter requests `wav`.
- `temperature` accepts 0.1..1.5. `speed` must be 1.0 (ADR-016); the speaking rate is applied after synthesis with ffmpeg `atempo`.
- The same seed, text, and voice produce the same audio. Output is 24 kHz mono.
- Errors: `{"error": {"message", "type", "code", "param"}}`. 400 means invalid request (not retried; `SynthesisError`). 503 means overloaded or not ready and carries a retry hint (`retry_after`); the transport retries with backoff and then raises `SynthesisError`.

**Voice cloning**

- `POST /v1/voices` with `{"voice_id", "ref_audio_b64" (base64 of wav or flac bytes), "ref_text", "lang", "mode": "icl_spk"|"icl"|"spk", "replace": bool}`.
- `GET /v1/voices` returns `{"voices": [...]}`; `DELETE /v1/voices/{id}` removes one.
- A registered `voice_id` is used as the `voice` field in `/v1/audio/speech`. Cross-lingual cloning is supported.
- The adapter registers the consented clip before the first synth using `voice_id = "as-{voice_id}-{clip_hash[:8]}"` with `replace=false`; a 409 or "exists" response is treated as success, which makes registration idempotent and ties the registered voice to the exact clip bytes. Default `mode` is `icl_spk` when `reference_text` is present, otherwise `spk`. The reference sent is `reference.24k.wav`.

**Languages**: `as, bn, en, gu, hi, kn, ml, mr, or, pa, ta, te`. Capabilities report these (English plus 11 Indian languages).

**Built-in voices (20)**: Ahana, Vaidehi, Malini, Charvi, Jahnavi, Anirban, Nakul, Vasant, Siddhant, Satvik, Abhay, Nivedita, Ishwari, Ritvik, Vrinda, Sreekar, Kayal, Shaunak, Akshat, Tanushree.

**In-process mode** (`maya2` extra, package `maya3`): `Maya3TTS.from_pretrained("maya-research/maya2-native", max_seats=N)`, `.generate(text, lang, voice)`, `.register_voice(name, ref_audio, ref_text, lang)`; returns 24 kHz float32. In-process mode is selected explicitly with `AUDIO_SMITH_MAYA2_MODE=inproc` (the URL always has a default, so it cannot signal the mode); otherwise HTTP.

**Adapter responsibilities**: language-code mapping, voice-id mapping and registration, `speed=1.0` enforcement plus post-synthesis `atempo`, `*word*` emphasis stripped (no inline emotion tags), and capabilities (`cloning: true`, `sample_rate: 24000`, `streaming: true`, `license: "Apache-2.0"`, `commercial_ok: true`).

### 6.7 Provider string format

LLM providers are selected with a provider string, parsed by `llm/__init__.py` (`parse_provider`):

| Provider | Format | Example |
|---|---|---|
| Ollama | `ollama:<model>` (model may contain `:`) | `ollama:qwen3:14b` |
| Anthropic | `anthropic:<model-id>` | `anthropic:claude-sonnet-5-5` |
| OpenAI-compatible | `openai_compat:<base_url>#<model>` | `openai_compat:http://127.0.0.1:8001/v1#qwen3-14b` |
| Fake (tests) | `fake` or `fake:<fixture-dir>` | `fake` |

TTS backends are selected by id (`maya2`, `kokoro`, `openai`, `openai_compat`, `chatterbox`, `mock`); HTTP backend base URLs come from settings (`AUDIO_SMITH_MAYA2_URL`, `AUDIO_SMITH_OPENAI_COMPAT_URL`).

Rules: unknown providers raise `UsageError` listing the known ids. API keys are never part of the string; they come from the environment or the OS keyring. The manifest records `generated_by` as `provider/model` without the base URL credentials.

---

## 7. Caching model

One module (`cache/keys.py`) computes all keys; `cache/store.py` reads and writes. No stage computes its own ad hoc key.

```
cache/
  v1/
    blocks/{blocks_key}.json           blocks_key = H(page bytes, extractor version,
                                                     parent_headings)
    scripts/{script_key}.md            script_key = H(content_hash, profile@ver, llm, lang,
                                                     writer prompt version, track)
    chunks/{chunk_key}.wav             chunk_key  = H(chunk_text_after_lexicon, backend,
                                                     model, voice_id, voice_clip_hash,
                                                     rate, seed)
    tracks/{track_key}.mp3
```

Additions and clarifications:

- `tracks/{track_key}` holds the finished MP3, VTT, optional Opus, and a JSON record of the track. The key covers every planned synthesis unit key plus the mastering signature (stings, bed, Opus, chunk pause, mastering version), so an unchanged page skips synthesis, QA, and ffmpeg (NFR-004, measured at about 0.6 s).
- Take 0 of a unit is cached under `chunks/`; QA retakes under `takes/`, with the best score in `takes/{key}.json`.

- Every key starts with the cache format (`v1-`), so bumping `CACHE_FORMAT` makes old entries unreachable instead of misread.
- The blocks key uses page bytes because the content hash is only known after extraction; the content hash (FR-003) is then computed from the normalized blocks.

- **Prompt template version in `script_key`:** `script_key = H(content_hash, profile@ver, llm, lang, prompt_template_version)`. The version is the content hash (or declared version header) of `script/prompts/writer.md` and, for translations, `translate.md`. Editing a prompt template therefore invalidates cached scripts automatically.
- **`track_key`:** `H(ordered chunk_keys, profile@ver mastering section, pause settings, sting and music-bed content hashes, tool major version)`.
- `H` is SHA-256 over a canonical, length-prefixed encoding of the inputs, hex-encoded and truncated to 32 characters for file names.
- The `v1` path segment is the cache layout version; a layout change bumps it and old data is ignored (and pruned).
- **Atomic writes:** entries are written to a temporary file in the same directory and moved into place with `os.replace`, so readers never see partial files and concurrent writers of the same key are safe (last writer wins with identical content). Reads verify the file is non-empty and, for WAV and MP3, that the header parses.
- **Prune:** `mr-audio-smith cache prune --older-than 30d` removes entries by last-access time (atime updated on read by the store), and `cache info` reports counts and sizes per kind. Pruning never touches the output directory or the voices directory.
- Hand-edited scripts are not stored in the cache; they live in the output directory and drive `chunk_key` through their text, so a changed paragraph re-synthesizes only that chunk.
- `--force` bypasses lookups but still writes entries.

---

## 8. Error model

Every failure raises a typed `AudioSmithError` subclass with `code`, `stage`, `message`, and `hint`. The CLI maps classes to exit codes. The server maps them to RFC 9457 problem+json. Stack traces are never printed unless `--debug`.

| Class | `code` | `stage` | Exit code |
|---|---|---|---|
| `AudioSmithError` (base) | `internal_error` | any | 1 |
| `UsageError` | `usage` | `config` | 2 |
| `PreflightError` | `preflight_failed` | `preflight` | 3 |
| `ExtractError` | `extract_failed` | `extract` | 4 |
| `FetchError` (subclass of `ExtractError`) | `fetch_failed` | `fetch` | 4 |
| `ScriptInvalidError` | `script_invalid` | `script` | 5 |
| `LLMError` | `llm_failed` | `script` | 5 |
| `SynthesisError` | `synthesis_failed` | `synth` | 6 |
| `MasteringError` | `mastering_failed` | `master` | 7 |
| `ConsentError` | `consent_missing` | `voice` | 8 |

Notes:

- `FetchError` (scheme not allowed, SSRF block, size or time limit, too many redirects, HTTP failure) maps to exit code 4 together with `ExtractError`.
- `hint` is always actionable (for example "Run `mr-audio-smith doctor`" or "Use `--allow-private` for local files").
- Messages and hints never contain secrets or the consent statement.
- `PreflightError` carries the full list of `PreflightIssue` objects.
- Unexpected exceptions are wrapped as `AudioSmithError(code="internal_error")` at the front door boundary.

---

## 9. Security model

Summary of the full Security Guidelines in the source prompt.

**Input handling**
- Fetch uses a scheme allowlist (`http`, `https`) and an SSRF guard that blocks 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fc00::/7, fe80::/10, and cloud metadata addresses unless `--allow-private` (`AUDIO_SMITH_ALLOW_PRIVATE`). The hostname is resolved once and the IP pinned for the connection. There are limits on size (`AUDIO_SMITH_MAX_FETCH_BYTES`, default 5 MiB), redirects, and time.
- HTML is parsed, never rendered or executed; there is no JavaScript engine in the pipeline.
- Extracted text is untrusted data in LLM prompts: wrapped in delimiters with an instruction that it is material to narrate, not instructions. The validator rejects output that deviates from Script Markdown, limiting prompt-injection impact to wording inside chunks.
- Path traversal guard: every output path, and every file name derived from URLs, is resolved and verified to be inside the output root.
- Subprocesses (ffmpeg) use argument arrays only, never shell strings.

**Voice cloning safety**
- A consent record is required for every cloned voice and is enforced in core (`ConsentError`), below every front door.
- Reference clips are stored with `0600` permissions in a `0700` directory and are never uploaded anywhere except the configured local or self-hosted TTS server.
- Manifests record the voice id only, never the clip or the consent statement.
- Docs state plainly: only clone your own voice or a voice you have written permission to use.
- A license guard refuses backends whose `commercial_ok` is false unless explicitly overridden.

**Server and Studio**
- Default bind is `127.0.0.1`. Binding elsewhere requires `AUDIO_SMITH_SERVER_TOKEN`; requests without the bearer token get 401.
- Studio uses a per-session random token, rejects requests without it, always binds 127.0.0.1, and sets `Content-Security-Policy: default-src 'self'; media-src 'self' blob:; connect-src 'self'`.
- CORS is disabled by default, with an explicit allowlist when enabled.
- Job artifacts are served only through the API with path validation.
- Rate limit on job creation per token (default 30 per hour).

**Dependency security**
- `uv.lock` and `bun.lockb` are committed; CI installs with `--frozen`.
- `pip-audit`, `npm audit --audit-level=high`, `gitleaks`, and Dependabot run in CI.
- Model weights are downloaded over HTTPS with pinned revisions and SHA-256 verification.
- Docker images run as non-root with a read-only root filesystem, no shell in the runtime CPU image (distroless where feasible), and are cosign-signed.

**Privacy**
- Zero telemetry; no analytics in the player or Studio.
- Local-first default (Ollama and local TTS). Cloud providers only when explicitly configured; `doctor` prints a "cloud providers active" warning when any are.
- The player stores only playback position in localStorage, inside try/catch.

**Secrets**
- API keys come only from environment variables or the OS keyring (`keyring`); never from `audio-smith.toml`, manifests, logs, or error messages. Logs redact any value whose key matches `*key*`, `*token*`, or `*secret*`.

---

## 10. Deployment topologies and configuration

### 10.1 Topologies

1. **Laptop or workstation (Tier 1):** CLI plus a local Maya 2 server (or in-process mode) on a Linux NVIDIA machine, or the Kokoro/mock backend elsewhere. Install with `uv tool install mr-audio-smith[...]` (primary; `pipx` as an alternative). `mr-audio-smith doctor` verifies the setup.
2. **GPU box on LAN (Tier 2):** for example a DGX Spark class machine running `mr-audio-smith serve` and the Maya 2 server (Docker Compose: `ollama`, `ollama-pull`, `maya2`, `audio-smith` services). Static-site CI calls it through `--server URL --token ...` or the GitHub Action's `server-url` input. The production compose file pins images by digest, sets CPU and memory limits, read-only root filesystems, an internal network for `ollama` and `maya2` (no published ports), publishes only `audio-smith` behind a TLS reverse proxy, with restart policies and log rotation. The Maya 2 health check targets port 8080 (not 8000).
3. **Kubernetes (Tier 3):** Helm chart `charts/mr-audio-smith`.
   - StatefulSet `maya2`: GPU (`nvidia.com/gpu: 1`), PVC `models` (50Gi), init container pre-downloads and checksums weights, readiness probe on `/health`.
   - StatefulSet `ollama` (optional, `ollama.enabled`): PVC 100Gi, init job pulls the script model; alternatively point at an existing vLLM OpenAI-compatible endpoint (on NVIDIA Grace arm64 nodes use `nvcr.io/nvidia/vllm-openai:latest`).
   - Deployment `audio-smith`: API layer, HPA on CPU and queue depth (custom metric), PVC `cache` (ReadWriteMany if replicas greater than 1) and `voices` (secret-like, 0700), Secret for `AUDIO_SMITH_SERVER_TOKEN`.
   - Ingress with TLS, `proxy-read-timeout: 600`, `proxy-body-size: 10m`, auth annotation.
   - NetworkPolicy so only `audio-smith` can reach `maya2` and `ollama`.
   - `values-k3s-gpu.yaml` for k3s with Cilium on a 2-node GPU cluster.
   - Note: the in-process queue and SQLite job store (ADR-012) mean `audio-smith` runs as a single replica for job processing in v1; additional replicas are read-only API replicas sharing the cache.

Packaging: PyPI, npm, GHCR images (CPU amd64/arm64, CUDA amd64/arm64), and the Helm chart. System requirement: `ffmpeg>=6.0` (libmp3lame, libopus, ebur128); CUDA 12.8 PyTorch wheels for Maya 2 on NVIDIA per its install instructions.

Environments: **dev** (laptop; mock or Kokoro; small Ollama model; everything on localhost), **stage** (GPU runner or LAN GPU box running Maya 2 and `serve`; TestPyPI rc builds; a staging copy of the reference site), **prod** (released packages; user machines; optional shared server for site automation). Example files: `.env.dev.example`, `.env.stage.example`, `.env.prod.example`.

### 10.2 Configuration precedence

From highest to lowest priority:

1. CLI flags
2. Environment variables with prefix `AUDIO_SMITH_` (plus the provider-standard `OLLAMA_HOST`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)
3. `audio-smith.toml`, discovered by walking upward from the current working directory to the filesystem root (first file found wins; `--config PATH` overrides discovery)
4. Built-in defaults

Unknown keys in `audio-smith.toml` produce a warning naming the key and file (not an error), so configuration written for a newer version still loads. Secrets are never read from `audio-smith.toml`; keys matching `*key*`, `*token*`, or `*secret*` in the file are ignored with a warning.

### 10.3 Environment variables

| Variable | dev | stage | prod | Notes |
|---|---|---|---|---|
| `AUDIO_SMITH_ENV` | `dev` | `stage` | `prod` | Affects defaults and log level |
| `AUDIO_SMITH_LOG_LEVEL` | `debug` | `info` | `info` | |
| `AUDIO_SMITH_LOG_FORMAT` | `pretty` | `json` | `pretty` (CLI) / `json` (server) | |
| `AUDIO_SMITH_CACHE_DIR` | `./.audio-smith/cache` | `/var/lib/audio-smith/cache` | `~/.cache/audio-smith` | |
| `AUDIO_SMITH_OUT_DIR` | `./out` | `/var/lib/audio-smith/out` | `./audio` | |
| `AUDIO_SMITH_VOICES_DIR` | `./voices` | `/var/lib/audio-smith/voices` | `~/.config/audio-smith/voices` | 0700 dir |
| `AUDIO_SMITH_DEFAULT_BACKEND` | `mock` | `maya2` | `maya2` | |
| `AUDIO_SMITH_MAYA2_URL` | `http://127.0.0.1:8080/v1` | `http://maya2:8080/v1` | `http://127.0.0.1:8080/v1` | Port 8080 is Maya 2's verified default (prompt said 8000) |
| `AUDIO_SMITH_LLM` | `ollama:qwen3:0.6b` | `ollama:qwen3:14b` | `ollama:qwen3:14b` | Any provider string |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | `http://ollama:11434` | `http://127.0.0.1:11434` | |
| `ANTHROPIC_API_KEY` | unset | optional | optional | Only if anthropic provider used |
| `OPENAI_API_KEY` | unset | optional | optional | Only if openai backend/provider used |
| `AUDIO_SMITH_SERVER_HOST` | `127.0.0.1` | `0.0.0.0` | `127.0.0.1` | Non-localhost needs token |
| `AUDIO_SMITH_SERVER_PORT` | `7340` | `7340` | `7340` | |
| `AUDIO_SMITH_SERVER_TOKEN` | unset | set (secret) | set if exposed | |
| `AUDIO_SMITH_STUDIO_PORT` | `7341` | `7341` | `7341` | Always 127.0.0.1 |
| `AUDIO_SMITH_QA_THRESHOLD` | `0.75` | `0.75` | `0.75` | Overrides profile `qa.threshold` |
| `AUDIO_SMITH_MAX_FETCH_BYTES` | `5242880` | `5242880` | `5242880` | |
| `AUDIO_SMITH_ALLOW_PRIVATE` | `true` | `false` | `false` | SSRF guard bypass |

Each variable maps to a `Settings` field in `config.py` (pydantic-settings) with the same name minus the prefix, lowercased. The Maya 2 compose service, Helm values, and probes use port 8080 in all environments.
