# Letters to a child: example project

A small static site of bedtime letters narrated in a parent's voice. It shows the project
settings, a profile override, a lexicon, the `data-narrate` markup, and the GitHub Action.

## Layout

- `audio-smith.toml`: default profile `kid-5`, default voice `dad`, outputs in `media/audio`.
- `profiles/kid-5.yaml`: overrides the built-in profile (version 1.1.0). The section headed
  "A grown-up note" becomes a separate parent track.
- `lexicon.yaml`: pronunciation respellings (Aadi, Houston).
- `letter-sample.html`: a letter using the markup below.
- `.github/workflows/narrate.yml`: narrate letters on push.

## Markup guide for letter templates

| Markup | Effect |
|---|---|
| `data-narrate` on a root element | Only this subtree is read. Put it on `<main>` or `<article>`. |
| `data-narrate="skip"` | Never read (newsletter promos, share buttons). |
| `data-narrate="parent"` | Goes to the parent track only, never into the child track. |
| `data-narrate-verbatim` | Read exactly as written; the script writer may not rephrase it. |
| `data-narrate-role="signature"` | The sign-off, read verbatim as the last chunk. |

## Register your voice (with consent)

```
mr-audio-smith voice add dad --clip dad.wav --name "Your Name" --relationship self
```

Only register a voice you own or have written permission to use. The clip stays on your machine
(or on your server). It is never written to the site repo.

## Narrate

One letter, with the mock backend (no GPU):

```
cd examples/letters-to-a-child
mr-audio-smith run letter-sample.html --backend mock --voice mock-a
mr-audio-smith inject letter-sample.html --manifest media/audio/letter-sample/letter-sample.manifest.json
```

Every letter linked from an index page (same origin only), then embed the player into local files:

```
mr-audio-smith site https://www.aadhish.us/messages-from-dad.html \
  --match "letter-*.html" --inject-root . --selector h1
```

Unchanged letters report `cached` and render nothing. The command exits 6 if any page failed.

## Run it from GitHub Actions

Copy `.github/workflows/narrate.yml` into your site repo. On every push that touches
`letter-*.html` the action narrates the changed letters, injects the player, and commits
`chore(audio): narrate N pages [skip ci]`. Use a self-hosted GPU runner, or set `server-url`
and `server-token` to use a remote `mr-audio-smith serve` (arrives with S7-T04).
