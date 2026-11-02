# Performance

Measurements for NFR-003 (end-to-end render time) and NFR-004 (unchanged re-run). Recorded during
Sprint 3 (S3-T11) on 2026-11-02.

## Machine

Apple M4, 24 GiB, macOS 15, Python 3.12, ffmpeg 8.1. Ollama 0.18 ran `qwen3:14b` on CPU on this host.

## Results

| Scenario | Input | Result | Target | Status |
|---|---|---|---|---|
| Kokoro on CPU, render + master | Reference letter, golden kid-5 script (28 chunks, 622 words) | 76 s wall time for 4 min 33 s of audio, including first-run downloads of Kokoro weights and the spaCy English model | under 10 min (NFR-003) | Met |
| Mock backend, full `run` (cold cache) | Reference letter fixture | 7.5 s without QA; 21.6 s with resemblyzer QA scoring every unit (synthesis 15.1 s, mastering 4.6 s) | n/a | Baseline |
| Unchanged re-run | Reference letter fixture, mock backend | 0.64 s | under 2 s (NFR-004) | Met |
| Script stage, live page | https://www.aadhish.us/letter-calm-in-the-chaos.html, `ollama:qwen3:14b` on CPU | about 10 min per LLM call | n/a | Note: Ollama used the CPU on this host; on Metal or an NVIDIA GPU expect well under a minute |
| Maya 2 on NVIDIA GPU | Reference letter | Not measured: no GPU runner is attached to this project yet | under 3 min (NFR-003) | Tracked as a manual step (TEST_PLAN `it_maya2_*`) |

## Where time goes

- Mastering is two ffmpeg passes (loudness measure, then normalize and encode) plus one measurement pass;
  about 4 to 5 s for a 4 minute letter.
- Synthesis dominates real backends. HTTP backends (Maya 2, OpenAI-compatible) run with a bounded
  concurrency of `AUDIO_SMITH_SYNTH_CONCURRENCY` (default 2) because the Maya 2 server serves concurrent
  streams; in-process backends (Kokoro, Chatterbox) run one unit at a time.
- Speaker similarity QA (resemblyzer) adds one embedding per unit; scores are cached with each take, so
  unchanged re-runs never recompute them.
- Finished tracks are cached under `cache/v1/tracks/`, so an unchanged page skips synthesis, QA, and
  ffmpeg entirely.

## How to reproduce

    cp tests/fixtures/golden/letter-calm.en.script.md out/perf/
    time uv run mr-audio-smith render out/perf/letter-calm.en.script.md --backend kokoro --voice am_michael --out out/perf
    time uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock --out out
    time uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock --out out
