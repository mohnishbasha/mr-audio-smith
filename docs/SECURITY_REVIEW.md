# Security review (S6-T01)

Sign-off date: 2026-11-02.

## Scope

- Python package `audio_smith` (fetch, extract, paths, voices and consent, TTS backends, master, publish, Studio).
- TypeScript: `player/`, `web/studio/`, `tests/e2e/`, `integrations/pi/`.
- Dependencies in `uv.lock` and the three `package-lock.json` files.
- Git history (40 commits at review time).
- Not in scope: the HTTP job server (`audio_smith/server`) and the MCP server (`audio_smith/mcp_server`) are empty
  placeholders in this tree, and no Docker image or Helm chart exists yet. Their checklist rows are marked N/A and
  must be reviewed when those front doors land.

## Method

1. Walked every item of the BUILD_PROMPT "Security Guidelines" checklist and ARCHITECTURE section 9 against the code.
2. Read `fetch.py` hop by hop for DNS rebinding and added tests that prove the connect target.
3. `pip-audit` on `uv export --frozen --no-dev` output, `npm audit --audit-level=high` per package, `gitleaks detect`.
4. Fuzzing the extractor with Hypothesis (token soup and generated HTML trees).
5. License policy check via `scripts/check-licenses.py --check`.

## Checklist results

| Item | Evidence | Status |
|---|---|---|
| Scheme allowlist (http, https, file, local path) | `audio_smith/fetch.py:26`, `fetch.py:262-289`; `test_fetch_non_http_scheme_rejected` | Pass |
| SSRF guard: private, loopback, link-local, CGNAT, metadata, IPv4-mapped IPv6 | `fetch.py:73-89`; `test_fetch_private_ip_blocked`, `test_fetch_private_ip_literal_and_any_answer_blocked` | Pass |
| Resolve once per hop and pin; connection goes to the vetted IP | `fetch.py:92-111` (`_pin_address`), `fetch.py:182-191` (`_pinned_request` rewrites the URL host to the IP, Host header and SNI keep the name), `fetch.py:196-198` | Pass |
| DNS rebinding cannot swap the IP between check and connect | `test_fetch_dns_rebinding_connects_to_resolved_ip` (resolver called once, request goes to first IP), new `test_fetch_rebinding_second_resolution_never_reaches_private_ip` (a private answer on a later hop is refused and never dialled), new `test_fetch_mixed_public_and_private_answers_rejected_whole` | Pass |
| Redirects revalidated per hop, capped, not auto-followed | `fetch.py:24`, `fetch.py:278` (`follow_redirects=False`), `test_fetch_redirect_to_private_blocked`, `test_fetch_redirect_limit_5_enforced` | Pass |
| Size, time, and content-type limits | `fetch.py:167-179`, `fetch.py:149-156`; `test_fetch_max_size_5mb_aborts_stream`, `test_fetch_total_time_budget_enforced` | Pass |
| HTML never executed | No JS engine or headless browser anywhere in `audio_smith`; extraction is selectolax and trafilatura only; `test_extract_*` hostile-page tests assert script content never appears | Pass |
| Extracted text is data in LLM prompts | `audio_smith/script/writer.py` delimiters, `script/validate.py` rejects deviations (ARCHITECTURE 9) | Pass (not re-reviewed beyond Sprint 2 tests) |
| Subprocess only via `proc.py`, argument arrays | `audio_smith/proc.py:9-40` (`TypeError` on a string); `grep subprocess` shows only `master/ffmpeg.py` catching `subprocess.SubprocessError`/`TimeoutExpired`; no `shell=True`, `os.system`, `eval`, `exec` | Pass |
| Path traversal: output paths and URL-derived names | `audio_smith/paths.py:16-40` (`safe_slug`, `ensure_inside`); used at `api.py:181`, `api.py:263`, `review_state.py:128`, `review.py:251`, `review.py:269`, `site.py:80`, `master/stings.py:51`; chunk ids are validated against the script before use in take file names (`review_render.py:204`); voice ids match `^[a-z0-9][a-z0-9-]{0,39}$` (`voices/registry.py:32`) | Pass |
| Studio media and inject routes confined | `test_studio_media_rejects_traversal_and_unknown_types`, `test_studio_inject_rejects_paths_outside_project_root`; media suffix allowlist in `review.py:269-273` | Pass |
| Consent enforced in core, below every front door | `voices/consent.py:113` (`require_consent` re-reads the on-disk record); called from `tts/maya2.py:101`, `tts/chatterbox.py:89`, `voices/registry.py:212,254`; `test_studio_render_unregistered_cloned_voice_is_403_consent` | Pass |
| License guard for non-commercial backends | `tts/license.py`, `--accept-noncommercial` in `cli_commands.py:115` | Pass |
| Voice files 0600 in 0700 directories | `voices/registry.py:36-37`, `:115-132`, repair at `:187-195`; POSIX permission tests in `test_voices.py` | Pass |
| Manifests carry no secrets, clip paths, or consent text | `publish/manifest.py:22` (`extra="forbid"`, voice id only) | Pass |
| Studio binds loopback only, no `--host` option | `studio/cli.py:15,42,48-55` | Pass |
| Studio per-session random token, constant-time compare | `studio/cli.py:36` (`secrets.token_urlsafe(24)`), `studio/routes.py:87-88` (`hmac.compare_digest` on `/api` and `/media`) | Pass |
| Studio CSP and hardening headers on every response | `studio/routes.py:25-33` (`default-src 'self'`, `frame-ancestors 'none'`, `nosniff`, `no-referrer`) | Pass |
| CORS disabled | No CORS middleware installed in `studio/routes.py` | Pass |
| Server bind default and bearer token off-loopback; job rate limit | `config.py:47-52` has the settings only; no server code exists | N/A (deferred) |
| Secrets only from env or keyring, never from the project file | `config.py:20,51,95-99` (secret-looking TOML keys ignored with a warning); API keys read from the environment in `llm/anthropic.py:46`, `llm/openai_compat.py:23`, `tts/openai_compat.py:112`; `keyring` is a declared dependency and no code path reads secrets from files | Pass |
| Log redaction of `*key*`, `*token*`, `*secret*` | Gap: structlog was a dependency but no processor existed. Fixed by new `audio_smith/logging.py` (`redact_secrets`, nested and `SecretStr` aware, bounded depth), `--log-format json`/`AUDIO_SMITH_LOG_FORMAT` wiring in `cli.py`; tests in `tests/unit/test_logging.py` and `regression_logs_redact_secret_named_keys_in_json_output` | Fixed |
| `Settings.redacted()` for display | `config.py:72-75` | Pass |
| Zero telemetry | `grep -ri "analytics\|telemetry\|sentry\|posthog\|mixpanel\|gtag"` over `audio_smith`, `player/src`, `web/studio/src` finds no usage; the player stores only playback position in `localStorage` inside try/catch (`player/src/player.ts:66-75`) | Pass |
| Dependabot configured | `.github/dependabot.yml` | Pass |
| Model weights pinned and hash-verified | Kokoro has `verify_weights` (`tts/kokoro.py:38`); Maya 2 and Chatterbox rely on the upstream libraries' Hugging Face downloads | Partial (see residual risks) |
| Docker: non-root, read-only rootfs, signed | No image exists yet | N/A (deferred) |

## Dependency audit results

Command: `uv export --frozen --no-dev ... --no-emit-project --no-hashes` then
`uv run pip-audit -r <file> --no-deps --disable-pip`.

Initial run (all extras, 92 advisories in 7 packages) and resolution:

| Package | Advisories | Resolution |
|---|---|---|
| starlette 0.52.1 (Studio, `server` extra) | 10 (Host header validation, request path validation, `request.form()` limits, Windows `StaticFiles`, `HTTPEndpoint` dispatch) | Fixed. `gradio==6.8.0` (demo-only transitive of `chatterbox-tts`) capped starlette below 1.0 for Python below 3.13. `[tool.uv] override-dependencies = ["starlette>=1.3.1"]` added to `pyproject.toml`; `uv lock` now resolves 1.10.0 on every Python. Studio tests pass. |
| torch 2.6.0 | 24 | Not fixable here: `chatterbox-tts==0.1.7` hard-pins `torch==2.6.0`. Not reachable: advisories are in specific tensor ops, `torch.compile`, and checkpoint loading. mr-audio-smith never passes untrusted tensors or untrusted checkpoints to torch; backends load pinned model files only. Several are disputed or have no fixed version. Core install (no ML extra) does not include torch. |
| transformers 5.2.0 | 6 | Pinned by `chatterbox-tts==0.1.7`. The advisories concern loading untrusted model repositories, `trust_remote_code`, and specific model classes (LightGlue). We never call `from_pretrained` on user-supplied repo ids and do not pass `trust_remote_code`. |
| diffusers 0.29.0 | 5 | Pinned by `chatterbox-tts`. Advisories are `trust_remote_code` bypasses in `DiffusionPipeline.from_pretrained`; diffusers pipelines are never used by this project. |
| gradio 6.8.0 | 5 | Pinned by `chatterbox-tts`. Gradio UI components (cookies, `FileExplorer`) are never imported or served by mr-audio-smith. |
| pillow 12.3.0 | 39 | Only reachable through gradio and diffusers (`chatterbox` extra); gradio caps it below 13. mr-audio-smith decodes no images. |
| setuptools 80.10.2 | 3 | Held below 81 deliberately (`qa` extra: resemblyzer needs `pkg_resources`, removed in later releases). Advisories affect building sdists and Windows wheel namespace handling, build-time only. |

After the fix, the core runtime closure (`--extra server --extra mcp --extra cloud`) reports no known
vulnerabilities. This is the blocking CI check. The optional ML extras (`kokoro`, `chatterbox`, `maya2`, `qa`)
are audited in a separate CI step with `continue-on-error`, so the residual items above stay visible.

npm (`npm audit --audit-level=high`):

| Project | Before | Resolution | After |
|---|---|---|---|
| `player/` | 4 critical, 1 high (dev only: vitest, @vitest/coverage-v8, happy-dom, tinypool, vite) | `vitest` and `@vitest/coverage-v8` to `^4.1.12`, `happy-dom` to `^21.0.4` | 0 high, 0 critical (11 moderate, dev tooling only) |
| `web/studio/` | same | same, plus `vite` to `^7.3.7` | 0 high, 0 critical |
| `tests/e2e/` | 0 | none | 0 |
| `integrations/pi/` | no lockfile, no dependencies | none | n/a |

`npm audit --omit=dev` reports 0 vulnerabilities for both shipped packages. Player and Studio unit tests, typecheck,
lint, and builds pass after the upgrade.

Licenses: `scripts/check-licenses.py --check` passes (190 Python and 1 npm package). See `THIRD_PARTY_LICENSES.md`.

## Secrets scan

`gitleaks detect --no-banner` (gitleaks installed via Homebrew): 40 commits, about 10.6 MB scanned, no leaks found.
CI runs `gitleaks/gitleaks-action@v2` on every push and pull request.

## Fuzzing

- `test_extract_blocks_fuzz_hypothesis_never_raises` (token soup, existing).
- New `test_extract_fuzz_generated_html_trees_never_crash`: nested, attribute-bearing HTML trees including `script`,
  `style`, `hidden`, and `onclick`; asserts no exception other than `ExtractError`, the total character cap holds, and
  no script text leaks into blocks.
- No crash found.

## Residual risks

1. **Resolved by the lead after the review:** the `chatterbox` extra was removed from `pyproject.toml` (its hard pins
   of torch, transformers, diffusers, gradio, and pillow carried about 80 advisories and capped starlette below 1.0),
   and torch, transformers, pillow, huggingface-hub, and numpy were upgraded in the lock (torch 2.15). A fresh
   `pip-audit` over every remaining extra reports only setuptools (below): users who want Chatterbox install
   `chatterbox-tts` themselves and accept its pins. The starlette override is no longer needed and was removed.
   Remaining: **setuptools 80.10.2** (PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w) is held below 81 because resemblyzer
   and webrtcvad import `pkg_resources`; the advisories concern package-index and build-time code paths that
   mr-audio-smith never calls (it only imports `pkg_resources` indirectly through the `qa` extra). Not reachable.
2. **Copyleft dependencies.** Resolved for the core: the lead replaced `mutagen` (GPL-2.0-or-later) with ffmpeg
   metadata writing in a separate process (`audio_smith/master/tags.py`), so the MIT core links no copyleft
   library. `phonemizer-fork` and `espeakng-loader` (GPL-3.0-or-later, pulled by the optional `kokoro` extra) stay
   allowlisted in `scripts/check-licenses.py`; none is bundled in our wheel, and a container image that includes
   them must ship license texts and source offers.
3. **Environment proxies.** `httpx.Client` honours `HTTP(S)_PROXY`. With a proxy the vetted IP is sent to the proxy,
   which then makes the connection, so the pin protects the request line but the proxy is trusted.
4. **Model weight integrity.** Only Kokoro verifies a SHA-256. Maya 2 and Chatterbox weights depend on the upstream
   Hugging Face client; pin revisions and hashes before v1.0.0 if the threat model includes a compromised upstream.
5. **Studio token in the URL.** The token is printed as a query parameter; it can land in shell history or terminal
   logs. It is per-session, loopback-only, and the page keeps it in memory.
6. **Server and MCP front doors** are not implemented, so bearer-token, rate-limit, and CORS controls are unreviewed.
7. npm moderate findings remain in dev tooling (eslint's minimatch, vite-adjacent packages). They never ship.

## Sign-off

Reviewer: Claude Code (Sprint 6 agent), for the project owner. Date: 2026-11-02.
No high or critical finding is left unresolved or unexplained: every high or critical advisory is either fixed or
documented above as pinned upstream and not reachable. Item 4 (model weight hashes for Maya 2) needs an owner decision; Maya 2 weights are downloaded by the upstream server, not by mr-audio-smith.
