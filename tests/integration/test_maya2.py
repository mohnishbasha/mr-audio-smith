"""Maya 2 integration against a live server (TEST_PLAN 5.8). Manual: needs a GPU runner."""

import os
from pathlib import Path

import pytest

from audio_smith.tts.base import SynthParams, VoiceRef
from audio_smith.tts.maya2 import Maya2Backend

CLEAN_WAV = Path(__file__).parent.parent / "fixtures" / "voices" / "clean.wav"
EXPECTED_RATE = 24_000

pytestmark = [pytest.mark.integration, pytest.mark.gpu]


def it_maya2_synth_clone_returns_24khz_mono() -> None:
    url = os.environ.get("AUDIO_SMITH_IT_MAYA2_URL")
    if not url:
        pytest.skip("AUDIO_SMITH_IT_MAYA2_URL not set")
    if not CLEAN_WAV.exists():
        pytest.skip("tests/fixtures/voices/clean.wav not present")
    backend = Maya2Backend(base_url=url)
    voice = VoiceRef(id="it-clean", reference_wav=CLEAN_WAV, reference_text=None, lang="en")
    pcm = backend.synth("This is an integration check.", voice, SynthParams())
    assert pcm.sample_rate == EXPECTED_RATE
    assert pcm.samples.ndim == 1 and len(pcm.samples) > 0
