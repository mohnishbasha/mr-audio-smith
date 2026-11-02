# Backends

A backend turns script text into speech. Choose one with `--backend` or `default_backend` in
`audio-smith.toml`. Run `mr-audio-smith doctor` to see which are ready.

| Id | Runs on | Cloning | Languages | Notes |
|---|---|---|---|---|
| `maya2` | NVIDIA GPU, Linux | yes, zero-shot | 12 (en, hi, mr, ta, te, bn, gu, kn, ml, or, pa, as) | Default. Apache-2.0 |
| `kokoro` | CPU | no, built-in voices | en, hi | Needs Python 3.12 and espeak-ng. Apache-2.0 |
| `openai` | OpenAI cloud | no | many | Needs `OPENAI_API_KEY`. Stock voices only |
| `openai_compat` | Any OpenAI-compatible TTS server | depends on server | depends | `AUDIO_SMITH_OPENAI_COMPAT_URL` |
| `chatterbox` | GPU or CPU | yes | en | Optional extra. MIT |
| `mock` | Anywhere | no | all | Deterministic placeholder audio for tests and dry runs |

## Maya 2 Native

Maya 2 is the default and the best match for cloning your own voice in 12 languages. It needs a
Linux machine with an NVIDIA GPU (about 8 GB of VRAM) and CUDA 12.8 drivers. It does not run on
Apple silicon (no MPS support).

The `maya3` package is not on PyPI, so install it from git next to the extra:

```bash
uv tool install --python 3.12 "mr-audio-smith[maya2,qa]"
uv pip install "maya3 @ git+https://github.com/MayaResearch/maya2-native@79142d835fc745537fc5ab71a007eba8f425c74c"
```

Launch the server (it listens on port 8080, not 8000):

```bash
python -m maya3.server --ckpt maya-research/maya2-native --host 127.0.0.1 --port 8080 --max-seats 2
```

The server returns HTTP 503 from `/health` while the model loads and 200 when ready. mr-audio-smith
waits and retries, so the first run after a start can take a minute or more.

GPU notes:

- One GPU worker handles synthesis; `--max-seats` sets how many requests the server accepts at once.
- Seeds make output repeatable: the same seed, text, and voice give the same audio.
- Speaking rate is applied after synthesis with ffmpeg, because the server only accepts speed 1.0.
- To run the model inside mr-audio-smith instead of a server, set `AUDIO_SMITH_MAYA2_MODE=inproc`.
- Point at a server elsewhere with `AUDIO_SMITH_MAYA2_URL=http://gpu-box:8080/v1`.

## Kokoro (CPU)

Kokoro is small and good enough for many pages, with no GPU and no cloning. It ships built-in
voices such as `af_heart`, `am_michael`, `bf_emma`, and `hf_alpha`.

```bash
uv tool install --python 3.12 "mr-audio-smith[kokoro]"
mr-audio-smith run page.html --backend kokoro --voice af_heart
```

Kokoro does not install on Python 3.13 or newer, so use `--python 3.12`. It also needs the
`espeak-ng` system package for phonemes.

## OpenAI and OpenAI-compatible servers

```bash
export OPENAI_API_KEY=sk-...
mr-audio-smith run page.html --backend openai --voice alloy
```

`openai` uses `AUDIO_SMITH_OPENAI_TTS_MODEL` (default `gpt-4o-mini-tts`). For a self-hosted server
that speaks the same API, set `AUDIO_SMITH_OPENAI_COMPAT_URL` (default `http://127.0.0.1:8000/v1`)
and use `--backend openai_compat`. These backends send your text to that server; `doctor` warns when
a cloud provider is active.

## Chatterbox

An optional cloning backend for English:

```bash
uv tool install --python 3.12 "mr-audio-smith[chatterbox]"
```

Like Kokoro it needs Python below 3.13.

## Mock

`--backend mock` writes deterministic placeholder audio with the built-in voices `mock-a` and
`mock-b`. Use it to try the pipeline, in CI, and in tests.

## License guard

Some model weights are licensed for non-commercial use only. A backend that declares this is refused
with a usage error (exit 2) unless you pass `--accept-noncommercial` or set
`AUDIO_SMITH_ACCEPT_NONCOMMERCIAL=true`. When you do, the manifest records a warning so the choice
stays visible. Every backend shipped by default is commercially usable. See
`THIRD_PARTY_LICENSES.md` for the license of each model.
