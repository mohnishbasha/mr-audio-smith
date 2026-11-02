"""Kokoro and Chatterbox backends against fake third-party modules (no network, no GPU)."""

import hashlib
import shutil
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from audio_smith.config import Settings
from audio_smith.errors import PreflightError, SynthesisError, UsageError
from audio_smith.tts import chatterbox as cb_mod
from audio_smith.tts.base import SynthParams, VoiceRef
from audio_smith.tts.chatterbox import ChatterboxBackend
from audio_smith.tts.kokoro import KokoroBackend, verify_weights

CHUNK = np.full(2400, 0.1, dtype=np.float32)


class FakeKPipeline:
    instances: ClassVar[list["FakeKPipeline"]] = []

    def __init__(self, lang_code: str, repo_id: str) -> None:
        self.lang_code = lang_code
        self.repo_id = repo_id
        self.calls: list[tuple[str, str, float]] = []
        FakeKPipeline.instances.append(self)

    def __call__(self, text: str, voice: str, speed: float) -> Iterator[tuple[str, str, Any]]:
        self.calls.append((text, voice, speed))
        yield ("g1", "p1", CHUNK)
        yield ("g2", "p2", CHUNK)


@pytest.fixture
def fake_kokoro(monkeypatch: pytest.MonkeyPatch) -> type[FakeKPipeline]:
    FakeKPipeline.instances = []
    mod = types.ModuleType("kokoro")
    mod.KPipeline = FakeKPipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kokoro", mod)
    return FakeKPipeline


def _voice(name: str, builtin: bool = True) -> VoiceRef:
    return VoiceRef(id=name, builtin=builtin)


def test_kokoro_synth_concatenates_chunks(fake_kokoro: type[FakeKPipeline]) -> None:
    audio = KokoroBackend().synth("Hello.", _voice("am_michael"), SynthParams())
    assert audio.sample_rate == 24_000
    assert len(audio.samples) == 2 * len(CHUNK)
    assert fake_kokoro.instances[0].repo_id == "hexgrad/Kokoro-82M"


def test_kokoro_rate_passthrough(fake_kokoro: type[FakeKPipeline]) -> None:
    KokoroBackend().synth("Hi", _voice("am_michael"), SynthParams(rate=1.25))
    assert fake_kokoro.instances[0].calls == [("Hi", "am_michael", 1.25)]


@pytest.mark.parametrize(("voice", "code"), [("af_heart", "a"), ("bf_emma", "b"), ("hm_omega", "h")])
def test_kokoro_lang_code_from_voice(fake_kokoro: type[FakeKPipeline], voice: str, code: str) -> None:
    be = KokoroBackend()
    be.synth("x", _voice(voice), SynthParams())
    be.synth("y", _voice(voice), SynthParams())
    assert [p.lang_code for p in fake_kokoro.instances] == [code]


def test_kokoro_rejects_non_builtin_voice(fake_kokoro: type[FakeKPipeline]) -> None:
    with pytest.raises(UsageError) as err:
        KokoroBackend().synth("x", _voice("my-clone", builtin=False), SynthParams())
    assert "am_michael" in (err.value.hint or "")


def test_kokoro_empty_audio_raises(fake_kokoro: type[FakeKPipeline], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeKPipeline, "__call__", lambda self, text, voice, speed: iter([("g", "p", None)]))
    with pytest.raises(SynthesisError):
        KokoroBackend().synth("x", _voice("am_michael"), SynthParams())


def test_kokoro_synth_without_package_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "kokoro", None)
    with pytest.raises(SynthesisError):
        KokoroBackend().synth("x", _voice("am_michael"), SynthParams())


def test_tts_capabilities_flags_per_backend() -> None:
    k = KokoroBackend.from_settings(Settings()).capabilities()
    assert (k.languages, k.cloning, k.sample_rate, k.max_chars) == (["en", "hi"], False, 24_000, 400)
    assert (k.license, k.commercial_ok, k.streaming) == ("Apache-2.0", True, False)
    assert "hm_omega" in k.builtin_voices
    c = ChatterboxBackend.from_settings(Settings()).capabilities()
    assert (c.languages, c.cloning, c.license, c.commercial_ok) == (["en"], True, "MIT", True)
    assert c.builtin_voices == ["default"]


def test_kokoro_preflight_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "kokoro", None)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/espeak-ng")
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    issues = KokoroBackend().preflight()
    assert [i.code for i in issues] == ["kokoro_missing"]
    assert "mr-audio-smith[kokoro]" in (issues[0].hint or "")


def test_doctor_python_313_hints_kokoro_use_312(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "kokoro", None)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/espeak-ng")
    monkeypatch.setattr(sys, "version_info", (3, 13, 0, "final", 0))
    hint = KokoroBackend().preflight()[0].hint or ""
    assert "3.12" in hint


def test_kokoro_preflight_espeak_missing_warning(
    fake_kokoro: type[FakeKPipeline], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    issues = KokoroBackend().preflight()
    assert [(i.severity, i.code) for i in issues] == [("warning", "espeak_missing")]
    assert "brew" in (issues[0].hint or "")


def test_kokoro_preflight_clean(fake_kokoro: type[FakeKPipeline], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/espeak-ng")
    assert KokoroBackend().preflight() == []


def test_kokoro_weights_checksum(tmp_path: Path) -> None:
    f = tmp_path / "kokoro.pth"
    f.write_bytes(b"weights")
    good = hashlib.sha256(b"weights").hexdigest()
    verify_weights(f, good)
    with pytest.raises(PreflightError) as err:
        verify_weights(f, "0" * 64)
    assert err.value.issues[0].severity == "error"


def test_kokoro_preflight_reports_weights_mismatch(
    fake_kokoro: type[FakeKPipeline], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/espeak-ng")
    f = tmp_path / "w.pth"
    f.write_bytes(b"abc")
    assert KokoroBackend(f, "0" * 64).preflight()[0].code == "kokoro_weights_checksum"
    assert KokoroBackend(f, hashlib.sha256(b"abc").hexdigest()).preflight() == []
    missing = KokoroBackend(tmp_path / "nope", "0" * 64).preflight()
    assert missing[0].code == "kokoro_weights_unreadable"


class FakeTensor:
    def squeeze(self) -> "FakeTensor":
        return self

    def cpu(self) -> "FakeTensor":
        return self

    def numpy(self) -> Any:
        return np.full(1000, 0.2, dtype=np.float32)


class FakeChatterbox:
    sr = 24_000
    device: str | None = None
    last_kwargs: ClassVar[dict[str, Any]] = {}

    @classmethod
    def from_pretrained(cls, device: str) -> "FakeChatterbox":
        cls.device = device
        return cls()

    def generate(self, text: str, **kwargs: Any) -> FakeTensor:
        FakeChatterbox.last_kwargs = kwargs
        return FakeTensor()


@pytest.fixture
def fake_chatterbox(monkeypatch: pytest.MonkeyPatch) -> type[FakeChatterbox]:
    pkg = types.ModuleType("chatterbox")
    tts = types.ModuleType("chatterbox.tts")
    tts.ChatterboxTTS = FakeChatterbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "chatterbox", pkg)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", tts)
    return FakeChatterbox


def test_chatterbox_builtin_voice_no_consent(fake_chatterbox: type[FakeChatterbox]) -> None:
    audio = ChatterboxBackend(device="cpu").synth("Hi", _voice("default"), SynthParams())
    assert audio.sample_rate == 24_000
    assert len(audio.samples) == 1000
    assert fake_chatterbox.last_kwargs == {}
    assert fake_chatterbox.device == "cpu"


def test_chatterbox_clone_requires_consent(
    fake_chatterbox: type[FakeChatterbox], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str] = []
    consent = types.ModuleType("audio_smith.voices.consent")
    consent.require_consent = lambda v: seen.append(v.id)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "audio_smith.voices.consent", consent)
    wav = tmp_path / "ref.wav"
    voice = VoiceRef(id="mom", reference_wav=wav)
    ChatterboxBackend(device="cpu").synth("Hi", voice, SynthParams())
    assert seen == ["mom"]
    assert fake_chatterbox.last_kwargs == {"audio_prompt_path": str(wav)}


def test_chatterbox_clone_without_reference_raises(
    fake_chatterbox: type[FakeChatterbox], monkeypatch: pytest.MonkeyPatch
) -> None:
    consent = types.ModuleType("audio_smith.voices.consent")
    consent.require_consent = lambda v: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "audio_smith.voices.consent", consent)
    with pytest.raises(UsageError):
        ChatterboxBackend(device="cpu").synth("Hi", VoiceRef(id="x"), SynthParams())


def test_chatterbox_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "chatterbox", None)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", None)
    issues = ChatterboxBackend().preflight()
    assert issues[0].code == "chatterbox_missing"
    with pytest.raises(SynthesisError):
        ChatterboxBackend(device="cpu").synth("x", _voice("default"), SynthParams())


def test_chatterbox_preflight_ok(fake_chatterbox: type[FakeChatterbox]) -> None:
    assert ChatterboxBackend().preflight() == []


def test_chatterbox_device_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = types.ModuleType("torch")
    state = {"cuda": False, "mps": False}
    torch.cuda = types.SimpleNamespace(is_available=lambda: state["cuda"])  # type: ignore[attr-defined]
    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: state["mps"]))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert cb_mod._pick_device() == "cpu"
    state["mps"] = True
    assert cb_mod._pick_device() == "mps"
    state["cuda"] = True
    assert cb_mod._pick_device() == "cuda"
    monkeypatch.setitem(sys.modules, "torch", None)
    assert cb_mod._pick_device() == "cpu"


def test_tts_chatterbox_rate_applied_post_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    import audio_smith.tts.chatterbox as cb
    from audio_smith.tts.base import PcmAudio, SynthParams, VoiceRef

    seen: list[float] = []

    def fake_rate(pcm: PcmAudio, rate: float) -> PcmAudio:
        seen.append(rate)
        return pcm

    monkeypatch.setattr(cb, "apply_rate", fake_rate)
    backend = cb.ChatterboxBackend()
    monkeypatch.setattr(backend, "_load", FakeChatterbox)
    backend.synth("Hello there.", VoiceRef(id="default", builtin=True), SynthParams(rate=0.9))
    assert seen == [0.9]
