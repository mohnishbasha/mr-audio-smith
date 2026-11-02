# File formats

Every persisted format carries a `schema` id with a major version, such as `audio-smith/blocks@1`.
The JSON Schemas live in [`schemas/`](https://github.com/mohnishbasha/mr-audio-smith/tree/develop/schemas):

| Format | Schema |
|---|---|
| Block JSON | [`blocks.schema.json`](https://github.com/mohnishbasha/mr-audio-smith/blob/develop/schemas/blocks.schema.json) |
| Script Markdown | [`script.schema.json`](https://github.com/mohnishbasha/mr-audio-smith/blob/develop/schemas/script.schema.json) (frontmatter) |
| Profile YAML | [`profile.schema.json`](https://github.com/mohnishbasha/mr-audio-smith/blob/develop/schemas/profile.schema.json) |
| Manifest JSON | [`manifest.schema.json`](https://github.com/mohnishbasha/mr-audio-smith/blob/develop/schemas/manifest.schema.json) |
| Voice record | [`voice.schema.json`](https://github.com/mohnishbasha/mr-audio-smith/blob/develop/schemas/voice.schema.json) |

`mr-audio-smith profile schema` prints the profile schema.

## Block JSON

`<slug>.blocks.json` is the extracted content of a page.

| Field | Meaning |
|---|---|
| `schema` | `audio-smith/blocks@1` |
| `source`, `title`, `lang` | Origin, document title, primary language subtag |
| `blocks[].id` | `bNNN`, stable within the document |
| `blocks[].type` | `title`, `heading`, `paragraph`, `list_item`, `quote`, `signature` |
| `blocks[].text` | Normalized text |
| `blocks[].track` | `main` or `parent` |
| `blocks[].index`, `blocks[].heading` | List position and owning heading for `list_item` |
| `blocks[].verbatim` | True when the text must not be changed |

## Script Markdown

`<slug>.<lang>.script.md` is the human-editable script.

```markdown
---
schema: audio-smith/script@1
source: https://example.com/letter.html
profile: kid-5@1.0.0
lang: en
content_hash: 9f2c...e1
generated_by: ollama/qwen3:14b
---

## 001
My dear Aadi... [pause 600]
Some days feel like a big, swirly storm!

## 003 {verbatim}
Your calm spot in every storm, Dad.
```

Rules the validator enforces:

- YAML frontmatter with `schema`, `source`, `profile` (`id@version`), `lang`, `content_hash`, and
  `generated_by` (use `human` for hand-written scripts). Unknown keys are rejected.
- Chunks start with `## NNN` (at least three digits), counting up from 001 with no gaps. Add
  ` {verbatim}` to a chunk that must match the source.
- Only two inline markers: `[pause N]` with N from 100 to 3000 milliseconds, and `*word*` for gentle
  emphasis on a single word.
- No lists, links, images, code, tables, HTML, or other Markdown in chunk text.
- A chunk may not exceed the effective maximum characters (profile value, capped by the backend).
  Two to four sentences per chunk is the target.

## Profile YAML

See [Profiles](../guide/profiles.md) for every field. Files live in `./profiles/<id>.yaml`.

## Manifest JSON

`<slug>.manifest.json` records what was made. It never contains secrets, reference clips, or consent
statements.

| Field | Meaning |
|---|---|
| `schema`, `tool_version` | `audio-smith/manifest@1` and the version that wrote it |
| `source`, `title`, `content_hash`, `created_at` | Origin, title, hash of normalized content, UTC time |
| `profile` | `{id, version}` |
| `backend` | `{id, model}` |
| `llm` | Provider string used for scripting |
| `voice_id` | The voice id only |
| `approved` | True after `--approve` or Studio approval |
| `tracks[]` | `lang`, `kind` (`main` or `parent`), `file`, `duration_s`, `loudness_lufs`, `true_peak_dbtp`, `peaks`, `captions`, optional `opus` |
| `chunks[]` | `id`, `hash`, `take`, `seed`, `similarity` (null when QA is unavailable), `duration_ms` |
| `timings` | Seconds per stage: fetch, extract, script, synth, master, publish |
| `warnings` | Human-readable warnings |

Mastered tracks target -16 LUFS with a true peak at or below -1.5 dBTP, 128 kbps mono MP3.

## Voice record

`voices/<id>/voice.yaml` (directory mode 0700, files 0600):

| Field | Meaning |
|---|---|
| `id`, `display_name` | Voice id (equals the directory name) and label |
| `backend_hints` | Backends the voice is expected to work with |
| `reference`, `reference_text` | Clip file name and its transcript |
| `consent.speaker_name`, `consent.relationship`, `consent.statement`, `consent.date` | The consent record |
| `clipcheck.*` | Duration, sample rate, SNR, and clipping measured at registration |
| `clip_hash` | SHA-256 of the clip, part of every chunk's cache key |

See [Voices and consent](../guide/voices-and-consent.md).
