# mr-audio-smith

*Every page deserves a voice.*

mr-audio-smith turns a web page into a realistic narration tuned for its listener, read in
your own cloned voice, generated on your own machine. It writes MP3, captions, and a one-tag
player you can drop into the page.

Part of the SnackOnAI smith family: mr-pixel-smith (images), mr-reel-smith (reels),
mr-motion-smith (motion), mr-audio-smith (audio).

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
- For Maya 2: an NVIDIA GPU with CUDA 12.8 drivers (Kokoro runs on CPU)

## Install

    uv tool install "mr-audio-smith[kokoro,qa]"
    mr-audio-smith doctor

## Quickstart

    # 1. Register your own voice (10 seconds, quiet room)
    mr-audio-smith voice add dad --clip my-voice.wav --name "Your Name" --relationship self

    # 2. Narrate a page for a five-year-old
    mr-audio-smith run https://example.com/letter.html --profile kid-5 --voice dad --inject letter.html

    # 3. Review and tweak in Studio
    mr-audio-smith studio

## Embed

    <audio-smith-player src="/media/audio/letter.mp3" captions="/media/audio/letter.vtt"
                        label="Listen to Dad read this letter" size="kid">
      <audio controls src="/media/audio/letter.mp3"></audio>
    </audio-smith-player>
    <script type="module" src="/media/audio/audio-smith-player.js"></script>

## Use from your agent

Claude Code, Goose, OpenCode: add the MCP server (`mr-audio-smith mcp`). Pi: install
`@mr-audio-smith/pi-extension`.

## Voice cloning ethics

Only clone your own voice, or a voice whose owner has given you written permission.
mr-audio-smith requires a consent record for every cloned voice.

## Build from source

    git clone https://github.com/mohnishbasha/mr-audio-smith && cd mr-audio-smith
    uv sync --all-extras --dev
    make lint typecheck test

## License

MIT © 2026 Serverless Ventures LLC. Model weights carry their own licenses; see
THIRD_PARTY_LICENSES.md.
```
