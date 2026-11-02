# Profiles

A profile describes the listener: how to write for them, how to speak to them, and how to master
the audio. Pick one with `--profile` (default `kid-5`, or `AUDIO_SMITH_DEFAULT_PROFILE`).

## Built-in profiles

| Id | Listener | Target length | Max sentence words | Speech rate | Chimes |
|---|---|---|---|---|---|
| `kid-5` | A five-year-old, bedtime or car ride | 5 min | 12 | 0.9 | soft intro and outro |
| `kid-8` | An eight-year-old who loves stories and facts | 7 min | 16 | 0.95 | soft intro and outro |
| `adult-commute` | An adult in the car or on a walk | 8 min | 22 | 1.0 | bright intro |
| `adult-brief` | A busy adult who wants the essentials | 2 min | 20 | 1.05 | none |

The kid profiles send grown-up-only content to a second track read with `adult-brief`.

```bash
mr-audio-smith profile list
mr-audio-smith profile show kid-5
mr-audio-smith profile validate profiles/my-profile.yaml
mr-audio-smith profile schema
```

## Profile fields

Unknown keys are validation errors, so typos never silently change behavior.

| Path | Type | Default | Constraints |
|---|---|---|---|
| `id` | string | required | `^[a-z0-9][a-z0-9-]{0,39}$`, unique among loaded profiles |
| `version` | string | required | Semantic version `MAJOR.MINOR.PATCH` |
| `description` | string | empty | Up to 200 characters |
| `audience.age` | int | none | 3 to 99 |
| `audience.attention_minutes` | number | none | Greater than 0; a longer script gets a warning |
| `writing.target_minutes` | number | 5 | 0.5 to 60 |
| `writing.max_sentence_words` | int | 20 | 4 to 60 |
| `writing.explain_big_words` | bool | false | |
| `writing.spoken_transitions` | bool | false | Adds signposting such as "Idea number two" |
| `writing.interactive_moments` | int | 0 | 0 to 10 |
| `writing.keep_signature_verbatim` | bool | true | Signature blocks become `{verbatim}` chunks |
| `writing.forbidden` | list of string | empty | Free-form tags passed to the writer prompt |
| `writing.parent_headings` | list of string | omitted | Heading texts routed to the parent track |
| `speech.rate` | number | 1.0 | 0.5 to 2.0 |
| `speech.pause_after_heading_ms` | int | 600 | 0 to 3000 |
| `speech.pause_between_chunks_ms` | int | 300 | 0 to 3000 |
| `speech.max_chunk_chars` | int | 400 | 80 to 400, capped by the backend |
| `languages` | list of string | `[en]` | Non-empty; one track per language |
| `tracks` | map | empty | Only key in v1: `parent`, naming another profile id |
| `mastering.intro_sting` | string or null | null | `builtin:chime-soft`, `builtin:chime-bright`, or a file path in the project |
| `mastering.outro_sting` | string or null | null | Same form |
| `mastering.music_bed` | string or null | null | `builtin:<name>` or a path; ducked under the voice |
| `lexicon` | map | empty | Written form to respelling, case-sensitive, up to 500 entries |
| `qa.takes_per_chunk` | int | 2 | 1 to 5 |
| `qa.threshold` | number | 0.75 | 0.0 to 1.0, minimum speaker similarity |

## Writing a custom profile

Say you want a calm, slower profile for bedtime stories, with a name pronounced correctly.

1. Create `profiles/bedtime.yaml` in your project:

    ```yaml
    id: bedtime
    version: 1.0.0
    description: Slow, soft bedtime stories for a toddler
    audience:
      age: 3
      attention_minutes: 4
    writing:
      target_minutes: 3
      max_sentence_words: 8
      explain_big_words: true
      interactive_moments: 1
      forbidden: [scary_detail, sarcasm]
    speech:
      rate: 0.85
      pause_after_heading_ms: 1000
      pause_between_chunks_ms: 500
    languages: [en]
    mastering:
      intro_sting: builtin:chime-soft
      outro_sting: builtin:chime-soft
    lexicon:
      Aadi: AH-dee
    ```

2. Validate it. Errors name the failing field path:

    ```bash
    mr-audio-smith profile validate profiles/bedtime.yaml
    ```

3. Use it:

    ```bash
    mr-audio-smith run story.html --profile bedtime --voice dad
    ```

Project profiles load from `./profiles` (change it with `profiles_dir` in `audio-smith.toml`). A
project profile with the same id as a built-in overrides it, which is how the
[letters example](https://github.com/mohnishbasha/mr-audio-smith/tree/develop/examples/letters-to-a-child)
customizes `kid-5`. Bump `version` when you change a profile, so cached scripts regenerate.

## Parent headings

Letters to a child often contain a section for the parent. `writing.parent_headings` routes those
sections to a separate parent track:

```yaml
writing:
  parent_headings: ["A grown-up note"]
tracks:
  parent: adult-brief
```

A container whose first child is a label matching one of the headings, or an `h2` to `h6` section
with a matching heading, goes to the parent track. The parent track is read with the profile named
under `tracks.parent` and saved as `<slug>.parent.mp3`. The setting is opt-in; if you leave it out,
track assignment comes only from `data-narrate="parent"` markup in your page.

## Pronunciation

`lexicon` entries (and an optional `lexicon.yaml` next to your project file) are applied when the
text is synthesized, not written into the script. Write the respelling the way you want it said:
`Houston: HYOO-stun`.
