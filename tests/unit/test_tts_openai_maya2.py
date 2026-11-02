"""Unit tests for the OpenAI-compatible and Maya 2 backends (TEST_PLAN 5.8). HTTP via respx."""

import importlib
import importlib.util
import io
import json
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import openai
import pytest
import respx
import soundfile as sf

from audio_smith.config import Settings
from audio_smith.doctor import check_python
from audio_smith.errors import ConsentError, SynthesisError, UsageError
from audio_smith.tts import checks as tts_checks
from audio_smith.tts import maya2 as maya2_mod
from audio_smith.tts.base import PcmAudio, SynthParams, VoiceRef
from audio_smith.tts.maya2 import Maya2Backend
from audio_smith.tts.openai_compat import OpenAICompatBackend, is_local_host
from audio_smith.tts.rate import apply_rate

# openai>=2 ships on httpx2, which respx cannot patch; older SDKs use httpx
sdk_httpx: Any = importlib.import_module("httpx2" if importlib.util.find_spec("httpx2") else "httpx")
VOICES = "http://127.0.0.1:8080/v1/voices"
HEALTH = "http://127.0.0.1:8080/health"
SR = 24_000


def wav_bytes(seconds: float = 0.5, sr: int = SR) -> bytes:
    t = np.arange(int(sr * seconds)) / sr
    buf = io.BytesIO()
    sf.write(buf, (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr, format="WAV", subtype="FLOAT")
    return buf.getvalue()


class Speech:
    """Scripted /audio/speech server for the SDK's own HTTP stack (queue of responses or errors)."""

    def __init__(self) -> None:
        self.queue: list[object] = []
        self.requests: list[dict[str, object]] = []

    def add(self, status: int = 200, content: bytes = b"", headers: dict[str, str] | None = None) -> "Speech":
        self.queue.append((status, content, headers or {}))
        return self

    def fail(self, exc: Exception) -> "Speech":
        self.queue.append(exc)
        return self

    def handler(self, request: Any) -> Any:
        self.requests.append(json.loads(request.content))
        item: Any = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(item, Exception):
            raise item
        status, content, headers = item
        return sdk_httpx.Response(status, content=content, headers=headers)

    def client(self, base_url: str) -> openai.OpenAI:
        http = sdk_httpx.Client(transport=sdk_httpx.MockTransport(self.handler))
        return openai.OpenAI(base_url=base_url, api_key="k", max_retries=0, http_client=http)


@pytest.fixture
def speech() -> Speech:
    return Speech().add(200, wav_bytes())


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def maya(sleeps: list[float], speech: Speech) -> Maya2Backend:
    return Maya2Backend(
        base_url="http://127.0.0.1:8080/v1",
        sleep=sleeps.append,
        client=speech.client("http://127.0.0.1:8080/v1"),
    )


@pytest.fixture
def clone_voice(tmp_path: Path) -> VoiceRef:
    ref = tmp_path / "ref.wav"
    ref.write_bytes(wav_bytes())
    return VoiceRef(
        id="dad", reference_wav=ref, reference_text="hello", clip_hash="3b1f9a7cdeadbeef", lang="en"
    )


@pytest.fixture(autouse=True)
def allow_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(maya2_mod, "require_consent", lambda v: None)


BUILTIN = VoiceRef(id="Ahana", builtin=True)


def test_tts_openai_compat_success_returns_pcm(speech: Speech) -> None:
    b = OpenAICompatBackend.compat(Settings())
    b._client = speech.client("http://127.0.0.1:8000/v1")
    pcm = b.synth("hi *there*", VoiceRef(id="v", builtin=True), SynthParams(rate=1.2))
    assert pcm.sample_rate == SR and pcm.samples.dtype == np.float32
    sent = speech.requests[0]
    assert sent["input"] == "hi there" and sent["speed"] == 1.2 and sent["response_format"] == "wav"


def test_tts_openai_compat_4xx_raises_no_retry(
    speech: Speech, maya: Maya2Backend, sleeps: list[float]
) -> None:
    speech.queue = []
    speech.add(400, b'{"error": {"message": "bad voice"}}', {"content-type": "application/json"})
    with pytest.raises(SynthesisError, match="bad voice"):
        maya.synth("t", BUILTIN, SynthParams())
    assert len(speech.requests) == 1 and sleeps == []


def test_tts_openai_compat_5xx_retries_with_backoff(
    speech: Speech, maya: Maya2Backend, sleeps: list[float]
) -> None:
    speech.queue = []
    speech.add(500).add(429).add(200, wav_bytes())
    maya.synth("t", BUILTIN, SynthParams())
    assert len(speech.requests) == 3 and len(sleeps) == 2 and sleeps[1] > 0


def test_tts_maya2_503_not_ready_retries_with_retry_after(
    speech: Speech, maya: Maya2Backend, sleeps: list[float]
) -> None:
    speech.queue = []
    speech.add(503, headers={"retry-after": "3"}).add(200, wav_bytes())
    maya.synth("t", BUILTIN, SynthParams())
    assert sleeps == [3.0]


def test_tts_openai_compat_timeout_raises(speech: Speech, maya: Maya2Backend, sleeps: list[float]) -> None:
    speech.queue = []
    speech.fail(sdk_httpx.ConnectTimeout("slow"))
    with pytest.raises(SynthesisError, match="3 attempts"):
        maya.synth("t", BUILTIN, SynthParams())
    assert len(speech.requests) == 3 and len(sleeps) == 2


def test_openai_compat_invalid_wav_raises(speech: Speech, maya: Maya2Backend) -> None:
    speech.queue = []
    speech.add(200, b"not a wav")
    with pytest.raises(SynthesisError, match="valid WAV"):
        maya.synth("t", BUILTIN, SynthParams())


def test_tts_maya2_request_body_matches_server_contract(speech: Speech, maya: Maya2Backend) -> None:
    maya.synth("hello *world*", BUILTIN, SynthParams(lang="hi", seed=7, temperature=0.7))
    body = speech.requests[0]
    assert body["model"] == "maya3" and body["voice"] == "Ahana" and body["language"] == "hi"
    assert body["speed"] == 1.0 and body["seed"] == 7 and body["temperature"] == 0.7
    assert body["response_format"] == "wav" and body["input"] == "hello world"


def test_tts_maya2_default_url_port_8080() -> None:
    assert Settings().maya2_url == "http://127.0.0.1:8080/v1"
    assert Maya2Backend.from_settings(Settings()).root == "http://127.0.0.1:8080"


def test_tts_maya2_supports_all_12_languages(maya: Maya2Backend) -> None:
    caps = maya.capabilities()
    assert sorted(caps.languages) == sorted(
        ["as", "bn", "en", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te"]
    )
    assert caps.cloning and caps.sample_rate == SR and len(caps.builtin_voices) == 20
    assert caps.license == "Apache-2.0" and caps.commercial_ok and caps.streaming


def test_tts_maya2_registers_clone_via_voices_endpoint_idempotent(
    respx_mock: respx.MockRouter, speech: Speech, maya: Maya2Backend, clone_voice: VoiceRef
) -> None:
    reg = respx_mock.post(VOICES).respond(201, json={})
    maya.synth("a", clone_voice, SynthParams())
    maya.synth("b", clone_voice, SynthParams())
    assert reg.call_count == 1
    payload = json.loads(reg.calls[0].request.content)
    assert payload["voice_id"] == "as-dad-3b1f9a7c" and payload["mode"] == "icl_spk"
    assert payload["replace"] is False and payload["ref_text"] == "hello"
    assert speech.requests[1]["voice"] == "as-dad-3b1f9a7c"


def test_maya2_registration_conflict_and_exists_are_success(
    respx_mock: respx.MockRouter, maya: Maya2Backend, clone_voice: VoiceRef
) -> None:
    respx_mock.post(VOICES).respond(409, json={"error": {"message": "voice exists"}})
    assert maya.map_voice(clone_voice) == "as-dad-3b1f9a7c"
    other = clone_voice.model_copy(update={"id": "mum", "reference_text": None})
    respx_mock.post(VOICES).respond(400, text="Voice already exists")
    assert maya.map_voice(other) == "as-mum-3b1f9a7c"


def test_maya2_registration_failures(
    respx_mock: respx.MockRouter, maya: Maya2Backend, clone_voice: VoiceRef
) -> None:
    respx_mock.post(VOICES).respond(422, text="bad clip")
    with pytest.raises(SynthesisError, match="rejected"):
        maya.map_voice(clone_voice)
    respx_mock.post(VOICES).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(SynthesisError, match="registration failed"):
        maya.map_voice(clone_voice)
    with pytest.raises(SynthesisError, match="no reference audio"):
        maya.map_voice(VoiceRef(id="x"))


def test_maya2_hash_derived_when_missing(
    respx_mock: respx.MockRouter, maya: Maya2Backend, clone_voice: VoiceRef
) -> None:
    respx_mock.post(VOICES).respond(200)
    v = clone_voice.model_copy(update={"clip_hash": None})
    assert maya.map_voice(v).startswith("as-dad-") and len(maya.map_voice(v)) == len("as-dad-") + 8


def test_consent_backend_refuses_clone_without_registry_entry(
    monkeypatch: pytest.MonkeyPatch, maya: Maya2Backend, clone_voice: VoiceRef
) -> None:
    def deny(_: VoiceRef) -> None:
        raise ConsentError("no consent")

    monkeypatch.setattr(maya2_mod, "require_consent", deny)
    with pytest.raises(ConsentError):
        maya.synth("t", clone_voice, SynthParams())


def test_maya2_unsupported_language_names_supported(maya: Maya2Backend) -> None:
    with pytest.raises(UsageError, match="does not support") as ei:
        maya.synth("t", BUILTIN, SynthParams(lang="fr"))
    assert "hi" in (ei.value.hint or "")


def test_tts_maya2_rate_applied_post_synthesis_atempo(speech: Speech, maya: Maya2Backend) -> None:
    pcm = maya.synth("t", BUILTIN, SynthParams(rate=2.0))
    assert speech.requests[0]["speed"] == 1.0
    assert 0.2 < pcm.duration_s < 0.3 and pcm.sample_rate == SR


def test_apply_rate_identity_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    pcm = PcmAudio(samples=np.zeros(100, dtype=np.float32), sample_rate=SR)
    assert apply_rate(pcm, 1.0) is pcm
    calls: list[list[str]] = []

    def boom(args: list[str], **_: object) -> bytes:
        calls.append(args)
        raise OSError("no ffmpeg")

    monkeypatch.setattr("audio_smith.tts.rate.proc.run", boom)
    with pytest.raises(SynthesisError, match="atempo"):
        apply_rate(pcm, 1.5)
    assert "atempo=1.5" in calls[0]


def test_maya2_preflight_ok_loading_unreachable(respx_mock: respx.MockRouter, maya: Maya2Backend) -> None:
    respx_mock.get(HEALTH).respond(200)
    assert maya.preflight() == []
    respx_mock.get(HEALTH).respond(503)
    issue = maya.preflight()[0]
    assert issue.code == "maya2.loading" and "still loading" in (issue.hint or "")
    respx_mock.get(HEALTH).mock(side_effect=httpx.ConnectError("refused"))
    issue = maya.preflight()[0]
    assert issue.code == "maya2.unreachable" and "maya3.server" in (issue.hint or "")


def test_openai_preflight_cloud_warning_and_key(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    respx_mock.get("https://api.openai.com/v1/models").respond(401)
    codes = [i.code for i in OpenAICompatBackend.cloud(Settings()).preflight()]
    assert codes == ["tts.openai_key_missing", "tts.cloud_active"]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cloud = OpenAICompatBackend.cloud(Settings())
    assert cloud.id == "openai" and cloud.capabilities().cloning is False
    assert [i.code for i in cloud.preflight()] == ["tts.cloud_active"]


def test_openai_compat_preflight_local_and_unreachable(respx_mock: respx.MockRouter) -> None:
    url = "http://127.0.0.1:8000/v1/models"
    b = OpenAICompatBackend.compat(Settings())
    respx_mock.get(url).respond(200, json={"data": []})
    assert b.preflight() == []
    respx_mock.get(url).respond(502)
    assert b.preflight()[0].code == "tts.unreachable"
    respx_mock.get(url).mock(side_effect=httpx.ConnectError("x"))
    assert b.preflight()[0].code == "tts.unreachable"


def test_is_local_host() -> None:
    assert is_local_host("http://localhost:1/v1") and is_local_host("http://10.0.0.5/v1")
    assert not is_local_host("https://api.openai.com/v1") and not is_local_host("http://8.8.8.8/v1")


class FakeEngine:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str, str | None, str]] = []

    def generate(self, text: str, lang: str, voice: str) -> np.ndarray[Any, Any]:
        return np.full(2400, 0.1, dtype=np.float32)

    def register_voice(self, name: str, ref_audio: str, ref_text: str | None, lang: str) -> None:
        self.registered.append((name, ref_audio, ref_text, lang))


def test_tts_maya2_inproc_mode_requires_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "maya3", None)
    b = Maya2Backend(base_url="http://127.0.0.1:8080/v1", mode="inproc")
    issue = b.preflight()[0]
    assert issue.code == "maya2.package_missing" and "git+https" in (issue.hint or "")
    with pytest.raises(SynthesisError, match="not installed"):
        b.synth("t", BUILTIN, SynthParams())


def test_maya2_inproc_with_fake_module(monkeypatch: pytest.MonkeyPatch, clone_voice: VoiceRef) -> None:
    engine = FakeEngine()
    seen: dict[str, object] = {}
    fake = types.ModuleType("maya3")

    class Maya3TTS:
        @staticmethod
        def from_pretrained(name: str, max_seats: int) -> FakeEngine:
            seen.update(name=name, max_seats=max_seats)
            return engine

    fake.Maya3TTS = Maya3TTS  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "maya3", fake)
    b = Maya2Backend.from_settings(Settings(maya2_mode="inproc"))
    assert b.preflight() == []
    assert b.synth("hi", BUILTIN, SynthParams()).samples.shape == (2400,)
    b.synth("hi", clone_voice, SynthParams())
    b.synth("hi", clone_voice, SynthParams())
    assert seen == {"name": "maya-research/maya2-native", "max_seats": 1}
    assert len(engine.registered) == 1 and engine.registered[0][0] == "as-dad-3b1f9a7c"


def test_backend_checks_one_row_per_backend_default_required(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    respx_mock.get(HEALTH).respond(200)
    respx_mock.get(url__regex=r".*/models").respond(200)
    s = Settings()
    rows = tts_checks.backend_checks(s)
    assert [r.name for r in rows] == [
        "tts:maya2",
        "tts:kokoro",
        "tts:chatterbox",
        "tts:openai",
        "tts:openai_compat",
    ]
    maya_row = rows[0].run(s)
    assert maya_row.ok and maya_row.required
    assert not rows[3].run(s).required


def test_backend_checks_failure_and_import_error(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    respx_mock.get(HEALTH).mock(side_effect=httpx.ConnectError("x"))
    res = tts_checks.backend_checks(Settings())[0].run(Settings())
    assert not res.ok and res.required and "maya3.server" in (res.hint or "")

    def missing(_id: str, _s: Settings) -> object:
        raise ImportError("no kokoro")

    monkeypatch.setattr(tts_checks, "get_backend", missing)
    res = tts_checks.backend_checks(Settings())[1].run(Settings())
    assert not res.ok and not res.required and "uv sync --extra kokoro" in (res.hint or "")


def test_gpu_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda _n: None)
    assert tts_checks.gpu_check(Settings()).detail == "torch not installed"
    fake = types.ModuleType("torch")
    fake.cuda = types.SimpleNamespace(is_available=lambda: True)  # type: ignore[attr-defined]
    monkeypatch.setattr(importlib.util, "find_spec", lambda _n: object())
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert tts_checks.gpu_check(Settings()).ok
    fake.cuda = types.SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    res = tts_checks.gpu_check(Settings())
    assert not res.ok and not res.required and res.hint


def test_doctor_default_checks_include_tts() -> None:
    from audio_smith.doctor import default_checks

    names = [c.name for c in default_checks()]
    assert "tts:maya2" in names and "gpu" in names and check_python(Settings()).ok
