# Quickstart

This walks you from a fresh machine to a narrated page in under ten minutes. You can follow the
dry run (mock backend, no models) first to check your setup, then switch to Kokoro on CPU for a
real voice. Maya 2 and voice cloning come after that.

## 1. Install the tools (2 minutes)

You need Python 3.12, [uv](https://docs.astral.sh/uv/), and ffmpeg 6 or newer.

```bash
# macOS
brew install ffmpeg espeak-ng
# Debian or Ubuntu
sudo apt install ffmpeg espeak-ng

uv tool install --python 3.12 "mr-audio-smith[kokoro,qa]"
mr-audio-smith doctor
```

!!! note
    Until v1.0.0 is on PyPI, install from a checkout instead:
    `git clone https://github.com/mohnishbasha/mr-audio-smith && cd mr-audio-smith && uv sync --all-extras --dev`,
    then prefix commands with `uv run`.

`doctor` prints a table of checks. Python and ffmpeg must be `ok`. GPU and cloud backend rows may
show `warn`; that is fine for this walkthrough.

## 2. Pick a script writer (2 minutes)

mr-audio-smith writes the narration script with a language model. The default is a local
[Ollama](https://ollama.com) model:

```bash
ollama pull qwen3:14b      # or a smaller model such as qwen3:4b on a laptop
export AUDIO_SMITH_LLM=ollama:qwen3:4b
```

You can also use `anthropic:<model-id>` with `ANTHROPIC_API_KEY`, or
`openai_compat:<base_url>#<model>`. Small models on CPU are slow; see
[Troubleshooting](troubleshooting.md).

## 3. Dry run with the mock backend (1 minute)

The mock backend makes deterministic placeholder audio, so you can check the whole pipeline
without any model weights. The `fake` LLM provider skips the script model as well.

```bash
cat > page.html <<'HTML'
<html><body><main data-narrate>
<h1>The Calm Eye of the Storm</h1>
<p>Some days feel like a big, swirly storm. Take a slow breath and look for the calm spot.</p>
<p data-narrate-role="signature">Your calm spot in every storm, Dad</p>
</main></body></html>
HTML

mr-audio-smith run page.html --llm fake --backend mock --voice mock-a --dry-run
mr-audio-smith run page.html --llm fake --backend mock --voice mock-a
```

Outputs land in `./audio/<slug>/`: an MP3, WebVTT captions, a script, and a manifest.

## 4. A real voice on CPU with Kokoro (3 minutes)

Kokoro ships built-in voices and needs no cloning. The first run downloads the model.

```bash
mr-audio-smith run page.html --backend kokoro --voice af_heart --profile kid-5 \
  --llm ollama:qwen3:4b --inject page.html
```

`--inject` adds the player to your page between the audio-smith markers. Open `page.html` in a
browser, serve the output folder next to it, and press play. Run the same command again: nothing is
re-rendered, because the cache says the page has not changed.

## 5. Your own voice (optional)

Cloning needs a backend that supports it (Maya 2 or Chatterbox). Record a clean 10 second clip
(see [Voices and consent](voices-and-consent.md)), then:

```bash
mr-audio-smith voice add dad --clip my-voice.wav --name "Your Name" --relationship self \
  --text "The words you said in the clip"
mr-audio-smith run page.html --profile kid-5 --voice dad --inject page.html
```

Start the Maya 2 server first; the [backends guide](backends.md) has the exact command.

## 6. Review in Studio

```bash
mr-audio-smith studio
```

Studio opens in your browser on 127.0.0.1. Edit chunks, compare takes, and approve. See
[Studio](studio.md).

## What next

- Tune the listener with [profiles](profiles.md)
- Narrate a whole site with [site mode](site-mode.md)
- Narrate on every push with the [GitHub Action](github-action.md)
