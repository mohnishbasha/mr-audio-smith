# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [1.0.0-rc.1] - 2026-11-02

### Added
- `mr-audio-smith --version` and `mr-audio-smith doctor` (Python, ffmpeg, cache directory, disk space checks, `--json` output).
- Configuration through `AUDIO_SMITH_*` environment variables and an `audio-smith.toml` project file.
- `mr-audio-smith script <url|file>` extracts a page and writes a reviewable Script Markdown file tuned to a listener profile, plus a separate parent script when the page has parent-only content.
- Safe page fetching: http(s) and local `.html`/`.md` files only, private and cloud-metadata addresses blocked (use `--allow-private` to opt in), 5 MB and 20 s limits.
- Content extraction honoring `data-narrate`, `data-narrate="skip"`, `data-narrate="parent"`, `data-narrate-verbatim`, and `data-narrate-role="signature"`; emoji, navigation, and list numbers are never narrated.
- Built-in audience profiles `kid-5`, `kid-8`, `adult-commute`, `adult-brief`, project profiles in `./profiles`, and `profile list|show|validate|schema`.
- Script writing with Ollama (default), Anthropic, or any OpenAI-compatible server, with one corrective retry when the script breaks the format.
- Pronunciation lexicon applied at synthesis time from the profile and an optional `lexicon.yaml`.
- `cache info` and `cache prune --older-than 30d`; unchanged pages are served from the cache.
- TTS backends behind one interface: Maya 2 Native (default, zero-shot cloning, 12 languages), Kokoro on CPU, OpenAI, any OpenAI-compatible server, Chatterbox (optional), and a deterministic mock.
- `mr-audio-smith voice add|list|check|remove` with a required consent record and clip quality checks (length, sample rate, clipping, noise); cloned voices are refused without consent from every entry point.
- `mr-audio-smith render <script.md> [--chunks 3,7]` synthesizes a reviewed script chunk by chunk, applying the pronunciation lexicon.
- `--accept-noncommercial` is required for backends whose weights are not licensed for commercial use.
- `doctor` now reports each backend, GPU visibility, the LLM provider, and registered voices.
- `mr-audio-smith run <url|file>` narrates a page end to end: a mastered MP3 (-16 LUFS, true peak at or below -1.5 dBTP, 128 kbps mono), WebVTT captions, ID3 tags with same-origin cover art, and a manifest, in `OUT/<slug>/`. `--approve` opens the script in `$EDITOR` first, `--dry-run` shows the plan, and an unchanged page re-runs in under two seconds.
- Content marked for grown-ups becomes a separate `<slug>.parent.mp3` read with the `adult-brief` profile.
- Speaker similarity checks for cloned voices (install the `qa` extra): weak chunks are re-rendered with a new seed and the best take is kept.
- Gentle original intro and outro chimes (`builtin:chime-soft`, `builtin:chime-bright`) and optional music bed ducking.
- `render <script.md>` now produces the mastered track; `--chunks 3,7` previews just those chunks as WAV files.
- Published JSON Schemas for blocks, scripts, profiles, voices, and manifests in `schemas/`.
- Python API: `audio_smith.narrate(source, profile=..., voice=..., backend=...)`.
- `<audio-smith-player>` web component (`@mr-audio-smith/player`, about 6.5 KB gzipped, no dependencies): breathing waveform, captions, language toggle, kid size, keyboard control, remembers your place, and a native audio fallback that works with JavaScript off.
- Every run writes `<slug>.embed.html` and copies the player script; `run --inject page.html` and `mr-audio-smith inject` add the player between `<!-- audio-smith:start -->` and `<!-- audio-smith:end -->` without touching anything else in the page.
- `embed_label`, `embed_size`, `embed_media_base`, and `embed_script_path` settings so a site configures its player once in `audio-smith.toml`.
- `run --lang en,hi` (or `languages` in the profile) adds translated tracks in the same voice, with chunks and pauses kept aligned.
- `mr-audio-smith site <index-url> --match "letter-*.html"` narrates every linked page, skips unchanged ones, and can inject into a local static-site checkout with `--inject-root`.
- `mr-audio-smith studio`: a local review UI on 127.0.0.1 (per-session token, strict Content-Security-Policy, no external requests). Edit chunks with live validation, render takes, compare two takes side by side and keep the better one, re-master and preview in the real player, approve, and inject with a diff preview.
- GitHub Action (`mohnishbasha/mr-audio-smith/action@v1`) narrates new or changed pages on push and commits the audio; example workflow and a complete letters-to-a-child example project.

### Fixed
- The signature and other verbatim passages are always kept exactly as written, even when the language model blanks or rephrases them.




### Security
- Logs redact any field whose name contains key, token, or secret; `--log-format json` for structured logs.
- Dependency audit (pip-audit, npm audit), secrets scan (gitleaks), and a license check run in CI; see docs/SECURITY_REVIEW.md.
- The Chatterbox backend is no longer an installable extra (its pinned dependencies carry unpatched advisories); install `chatterbox-tts` yourself to use it.
- ID3 tags are written with ffmpeg instead of a GPL-licensed library, keeping the MIT core free of copyleft code.

[Unreleased]: https://github.com/mohnishbasha/mr-audio-smith/compare/v1.0.0-rc.1...develop
[1.0.0-rc.1]: https://github.com/mohnishbasha/mr-audio-smith/releases/tag/v1.0.0-rc.1
