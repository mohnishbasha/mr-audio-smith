# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed

### Deprecated

### Removed

### Fixed

### Security

[Unreleased]: https://github.com/mohnishbasha/mr-audio-smith/compare/main...develop
