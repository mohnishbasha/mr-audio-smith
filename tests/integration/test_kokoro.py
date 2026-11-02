"""Kokoro on CPU, real model (needs the kokoro extra, espeak-ng, and Hugging Face access)."""

import importlib.util

import pytest

from audio_smith.tts.base import SynthParams, VoiceRef
from audio_smith.tts.kokoro import KokoroBackend

MIN_DURATION_S = 0.3


@pytest.mark.integration
def it_kokoro_synth_cpu_returns_audio() -> None:
    if importlib.util.find_spec("kokoro") is None:
        pytest.skip("kokoro is not installed")
    audio = KokoroBackend().synth("Hello Aadi.", VoiceRef(id="am_michael", builtin=True), SynthParams())
    assert audio.sample_rate == 24_000
    assert audio.duration_s > MIN_DURATION_S
