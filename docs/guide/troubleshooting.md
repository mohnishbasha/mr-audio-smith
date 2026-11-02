# Troubleshooting

Start with `mr-audio-smith doctor`. Add `--json` for machine-readable output.

```text
check             status  detail
python            ok      3.12.12
ffmpeg            ok      8.1 at /opt/homebrew/bin/ffmpeg
cache_dir         ok      ...
disk_space        ok      240.1 GiB free
llm               ok      ollama/qwen3:14b
voices            ok      none registered
tts:maya2         ok      ready
tts:kokoro        ok      ready
gpu               warn    CUDA not available
```

Each row has a status (`ok`, `warn`, or `fail`) and a hint on how to fix it. A `warn` for a backend
you do not use is fine.

## ffmpeg is missing

`doctor` shows `ffmpeg` as failing and runs exit 3 (preflight). Install ffmpeg 6 or newer:
`brew install ffmpeg` or `sudo apt install ffmpeg`. It must include libmp3lame.

## Maya 2 says 503 or "loading"

The Maya 2 server answers `/health` with 503 until the model has loaded, which takes a minute or
more on first start. Wait for 200, then retry. Check the URL (`AUDIO_SMITH_MAYA2_URL`, port 8080
by default) and that the server is running. `doctor` shows `tts:maya2` as unreachable otherwise.
Maya 2 needs a Linux NVIDIA GPU; on a Mac use Kokoro or point at a remote server.

## Kokoro will not install on Python 3.13

Kokoro supports Python below 3.13. Install with 3.12:
`uv tool install --python 3.12 "mr-audio-smith[kokoro]"`. If `doctor` says `espeak-ng not found`,
install it (`brew install espeak-ng` or `sudo apt install espeak-ng`).

## Ollama is slow on CPU

Script writing with a 14B model on CPU can take many minutes. Use a smaller model
(`AUDIO_SMITH_LLM=ollama:qwen3:4b`), run Ollama on a GPU machine and set `OLLAMA_HOST`, or use a
hosted provider (`anthropic:<model-id>`). Once a script exists it is cached, and you can review it
with `script`, then `render`.

## Exit code 8: consent error

The voice has no complete consent record, or its clip changed after registration. Run
`mr-audio-smith voice check <id>`. Re-register with `voice add ... --replace` and provide
`--name`, `--relationship`, and a statement. This check cannot be bypassed.

## Exit code 5: script invalid

The script broke the Script Markdown format (a bad chunk heading, a pause outside 100 to 3000 ms,
an over-length chunk, a rewritten verbatim passage) or the language model failed. The writer retries
once on its own. If you edited the script by hand, the error names the line; fix it and run
`render` again. A model that cannot follow the format (very small models) fails here; try a larger
one.

## Other exit codes

| Code | Meaning | First thing to try |
|---|---|---|
| 2 | Usage or configuration | Read the hint; for non-commercial weights pass `--accept-noncommercial` |
| 3 | Preflight failed | Run `doctor` |
| 4 | Fetch or extract failed | Check the URL; use `--allow-private` for local servers |
| 6 | Synthesis failed (or `site` had failures) | Check the backend with `doctor` |
| 7 | Mastering failed | Check ffmpeg |

The full table is in the [CLI reference](../reference/cli.md#exit-codes). Add `--debug` for a stack trace.

## The cache

Unchanged pages are skipped, which is why a second run takes seconds. To force a re-render use
`--force`. To see and trim the cache:

```bash
mr-audio-smith cache info
mr-audio-smith cache prune --older-than 30d
```

## Speaker similarity warnings

A manifest warning about low similarity means a cloned chunk stayed under the threshold after
retakes. Re-record a cleaner reference clip, raise `takes_per_chunk`, or fix that chunk in
[Studio](studio.md). Install the `qa` extra if the check is skipped.
