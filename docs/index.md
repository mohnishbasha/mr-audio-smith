# mr-audio-smith

*Every page deserves a voice.*

mr-audio-smith turns a web page into a realistic narration tuned for its listener, read in your
own cloned voice, generated on your own machine. It writes MP3, captions, and a one-tag player you
can drop into the page.

[Get started](guide/quickstart.md){ .md-button .md-button--primary }
[CLI reference](reference/cli.md){ .md-button }

!!! note "Status"
    v1.0.0 packages on PyPI and npm are published by the maintainer once trusted publishing is
    configured. Until then, install from source (`git clone` and `uv sync --all-extras --dev`).

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
- For Maya 2: a Linux machine with an NVIDIA GPU (about 8 GB VRAM) and CUDA 12.8 drivers. Run the
  Maya 2 server on port 8080; the `maya3` package is installed from git, not PyPI
- For Kokoro (CPU): Python 3.12, because Kokoro does not install on Python 3.13 yet

## Install

    uv tool install --python 3.12 "mr-audio-smith[kokoro,qa]"
    mr-audio-smith doctor

The `qa` extra adds the speaker similarity check for cloned voices. For Maya 2, start its server
(`python -m maya3.server --ckpt maya-research/maya2-native --host 127.0.0.1 --port 8080`); see the
[backends guide](guide/backends.md) for the git install.

## Quickstart

    # 1. Register your own voice (10 seconds, quiet room)
    mr-audio-smith voice add dad --clip my-voice.wav --name "Your Name" --relationship self

    # 2. Narrate a page for a five-year-old and add the player to your local copy
    mr-audio-smith run https://example.com/letter.html --profile kid-5 --voice dad --inject letter.html

    # 3. Review and tweak in Studio
    mr-audio-smith studio

No GPU yet? Try a dry run with the mock backend: `mr-audio-smith run page.html --backend mock --voice mock-a`.
Narrate a whole site with `mr-audio-smith site <index-url> --match "letter-*.html"`.

From Python:

    import audio_smith
    result = audio_smith.narrate("letter.html", profile="kid-5", voice="dad")

## Embed

    <audio-smith-player src="/media/audio/letter.mp3" captions="/media/audio/letter.vtt"
                        label="Listen to Dad read this letter" size="kid">
      <audio controls src="/media/audio/letter.mp3"></audio>
    </audio-smith-player>
    <script type="module" src="/media/audio/audio-smith-player.js"></script>

`run --inject page.html` (or `mr-audio-smith inject`) writes this between
`<!-- audio-smith:start -->` and `<!-- audio-smith:end -->` and touches nothing else in your page.
Without JavaScript, visitors still get the native audio controls.

## Use from your agent

Claude Code, Goose, OpenCode: add the MCP server (`mr-audio-smith mcp`, stdio or streamable
HTTP; install the `mcp` extra). Pi: install `@mr-audio-smith/pi-extension`. A GPU box can run
`mr-audio-smith serve` so laptops and CI narrate through it with `run --server URL --token ...`.

## Voice cloning ethics

Only clone your own voice, or a voice whose owner has given you written permission.
mr-audio-smith requires a consent record for every cloned voice. Clips never leave your machine
or your own server, and they are never written into a site repository.

## Where to go next

- [Quickstart](guide/quickstart.md): a narrated page in under ten minutes
- [Voices and consent](guide/voices-and-consent.md): record a clip and register your voice
- [Profiles](guide/profiles.md): tune the writing and speech for each listener
- [Backends](guide/backends.md): Maya 2, Kokoro, OpenAI, and friends
- [GitHub Action](guide/github-action.md): narrate on every push
- [CLI reference](reference/cli.md) and [Python API](reference/python-api.md)

MIT license, 2026 Serverless Ventures LLC. Model weights carry their own licenses.
