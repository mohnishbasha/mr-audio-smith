"""Registry, mock backend determinism, base helpers, and the license guard."""

import sys
import types

import numpy as np
import pytest

from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.tts.base import Capabilities, PcmAudio, SynthParams, VoiceRef, to_float32
from audio_smith.tts.license import check_license
from audio_smith.tts.mock import MockBackend
from audio_smith.tts.registry import BACKEND_IDS, FACTORIES, get_backend


def _synth(text: str, voice: str = "mock-a", rate: float = 1.0) -> PcmAudio:
    return MockBackend().synth(text, VoiceRef(id=voice, builtin=True), SynthParams(rate=rate))


def _caps(commercial_ok: bool) -> Capabilities:
    return Capabilities(
        languages=["en"], cloning=False, builtin_voices=[], sample_rate=24_000, max_chars=400,
        streaming=False, license="CC-BY-NC", commercial_ok=commercial_ok,
    )  # fmt: skip


def test_tts_registry_lists_all_backends() -> None:
    assert set(BACKEND_IDS) == set(FACTORIES)
    assert {"maya2", "kokoro", "chatterbox", "openai", "openai_compat", "mock"} == set(BACKEND_IDS)


def test_get_backend_mock_and_unknown() -> None:
    assert get_backend("mock", Settings()).id == "mock"
    with pytest.raises(UsageError) as err:
        get_backend("nope", Settings())
    assert "mock" in (err.value.hint or "")


def test_get_backend_kokoro_and_chatterbox_lazy() -> None:
    assert get_backend("kokoro", Settings()).id == "kokoro"
    assert get_backend("chatterbox", Settings()).id == "chatterbox"


def test_tts_mock_deterministic_across_runs() -> None:
    assert np.array_equal(_synth("Hello there").samples, _synth("Hello there").samples)
    assert MockBackend().preflight() == []


def test_tts_mock_pitch_derived_from_voice_id() -> None:
    assert not np.array_equal(_synth("Hello", "mock-a").samples, _synth("Hello", "mock-b").samples)


def test_tts_mock_duration_proportional_to_text_length() -> None:
    short, long = _synth("a" * 20), _synth("a" * 40)
    assert long.duration_s == pytest.approx(2 * short.duration_s, rel=0.01)
    assert _synth("a" * 20, rate=2.0).duration_s < short.duration_s


def test_pcm_duration_zero_rate() -> None:
    assert PcmAudio(samples=np.zeros(10, dtype=np.float32), sample_rate=0).duration_s == 0.0
    assert PcmAudio(samples=np.zeros(24_000, dtype=np.float32), sample_rate=24_000).duration_s == 1.0


def test_to_float32_int16_and_stereo() -> None:
    out = to_float32(np.array([0, 32767, -32767], dtype=np.int16))
    assert out.dtype == np.float32
    assert out[1] == pytest.approx(1.0)
    stereo = to_float32(np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float64))
    assert stereo.shape == (2,)
    assert stereo[0] == pytest.approx(0.5)
    assert to_float32(np.array([2.0, -3.0])).tolist() == [1.0, -1.0]


def test_tts_license_guard_noncommercial_requires_flag() -> None:
    assert check_license("x", _caps(True), False) == []
    with pytest.raises(UsageError):
        check_license("x", _caps(False), False)


def test_tts_license_guard_flag_recorded_in_manifest_warnings() -> None:
    warnings = check_license("x", _caps(False), True)
    assert len(warnings) == 1 and "CC-BY-NC" in warnings[0]


def test_registry_maya2_and_openai_factories_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        id = "fake"

        @classmethod
        def from_settings(cls, s: Settings) -> "Fake":
            return cls()

        cloud = compat = from_settings

    maya = types.ModuleType("audio_smith.tts.maya2")
    maya.Maya2Backend = Fake  # type: ignore[attr-defined]
    oai = types.ModuleType("audio_smith.tts.openai_compat")
    oai.OpenAICompatBackend = Fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "audio_smith.tts.maya2", maya)
    monkeypatch.setitem(sys.modules, "audio_smith.tts.openai_compat", oai)
    for backend_id in ("maya2", "openai", "openai_compat"):
        assert get_backend(backend_id, Settings()).id == "fake"
