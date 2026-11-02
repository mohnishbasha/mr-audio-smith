"""Mock backend: deterministic tones for tests and dev (no network, no GPU).

Duration is proportional to text length and pitch is derived from the voice id, so golden
tests can assert timing and identity without real speech.
"""

import hashlib

import numpy as np

from audio_smith.preflight import PreflightIssue
from audio_smith.tts.base import Capabilities, PcmAudio, SynthParams, VoiceRef

SAMPLE_RATE = 24_000
MS_PER_CHAR = 55
MIN_MS = 250
AMPLITUDE = 0.3
BASE_HZ = 110.0
PITCH_SPAN_HZ = 220.0
FADE_MS = 8


def pitch_for(voice_id: str) -> float:
    digest = int(hashlib.sha256(voice_id.encode()).hexdigest()[:8], 16)
    return BASE_HZ + (digest % 1000) / 1000 * PITCH_SPAN_HZ


def duration_ms(text: str, rate: float = 1.0) -> int:
    return max(MIN_MS, round(len(text) * MS_PER_CHAR / rate))


class MockBackend:
    id = "mock"
    model = "mock-tone-1"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            languages=["en", "hi", "mr", "ta", "te", "bn", "gu", "kn", "ml", "or", "pa", "as"],
            cloning=True,
            builtin_voices=["mock-a", "mock-b"],
            sample_rate=SAMPLE_RATE,
            max_chars=400,
            streaming=False,
            license="MIT",
            commercial_ok=True,
        )

    def preflight(self) -> list[PreflightIssue]:
        return []

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        n = SAMPLE_RATE * duration_ms(text, params.rate) // 1000
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
        wave = AMPLITUDE * np.sin(2 * np.pi * pitch_for(voice.id) * t)
        fade = min(n // 2, SAMPLE_RATE * FADE_MS // 1000)
        if fade:
            ramp = np.linspace(0.0, 1.0, fade)
            wave[:fade] *= ramp
            wave[-fade:] *= ramp[::-1]
        return PcmAudio(samples=wave.astype(np.float32), sample_rate=SAMPLE_RATE)
