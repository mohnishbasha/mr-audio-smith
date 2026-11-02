# GitHub Action

The action narrates new or changed pages when you push, injects the player, and commits the audio
back to your repository.

## Inputs

| Input | Default | Description |
|---|---|---|
| `pages-glob` | `*.html` | Glob of page files to narrate, matched against changed files (for example `letter-*.html`) |
| `site-url` | empty | Public base URL of the site, used to map files to page URLs |
| `profile` | empty | Profile id (`kid-5`, `adult-brief`, or a project profile) |
| `voice` | empty | Registered voice id. Voice clips live on the runner or server and are never committed |
| `backend` | empty | TTS backend id |
| `llm` | empty | LLM provider string, for example `ollama:qwen3:14b` |
| `server-url` | empty | Remote `mr-audio-smith serve` URL instead of a local GPU |
| `server-token` | empty | Bearer token for `server-url`; pass it from a secret |
| `commit` | `true` | Commit the generated audio and edited pages |
| `output-dir` | `media/audio` | Directory for generated audio, captions, and manifests |
| `image-tag` | `0.0.1` | mr-audio-smith version to install |
| `python-version` | `3.12` | Python version for the tool environment |

Output: `count`, the number of pages narrated. The commit message is
`chore(audio): narrate N pages [skip ci]`.

## Example workflow

```yaml
name: narrate
on:
  push:
    branches: [main]
    paths: ["letter-*.html"]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  narrate:
    runs-on: [self-hosted, gpu]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: mohnishbasha/mr-audio-smith/action@v1
        with:
          pages-glob: "letter-*.html"
          site-url: https://www.example.com
          profile: kid-5
          voice: dad
          output-dir: media/audio
```

`fetch-depth: 0` lets the action diff the push. Manual runs (`workflow_dispatch`) and first pushes
narrate every matching page; the cache skips the unchanged ones.

## Where the voice lives: two options

**Self-hosted GPU runner.** Register the voice on the runner machine
(`mr-audio-smith voice add ...`), run the Maya 2 server there, and use `runs-on: [self-hosted, gpu]`.
The reference clip never leaves that machine.

**Hosted runner plus a server.** Set `server-url` and `server-token` (from a repository secret) to
send synthesis to your own `mr-audio-smith serve` instance behind TLS. The server holds the voices.
The `serve` command arrives after v1.0.0; until then use the self-hosted runner option.

Either way, voice clips are never staged: the commit step only adds the output directory and the
pages it edited.

## Security notes

- Pin the action to a tag (`@v1`) or a commit SHA.
- Give the job only `contents: write`.
- Pass tokens as secrets, never inline.
- Do not run the workflow on pull requests from forks, which cannot read secrets and should not
  reach your GPU runner.
