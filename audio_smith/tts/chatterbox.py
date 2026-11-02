"""Chatterbox backend: optional MIT-licensed cloning model, GPU recommended (ADR-014).

The `chatterbox` package is imported lazily so this module loads without the extra.
Cloning goes through the consent gate before any reference audio reaches the model.
"""

from typing import Any

import numpy as np

from audio_smith.config import Settings
from audio_smith.errors import SynthesisError, UsageError
from audio_smith.preflight import PreflightIssue
from audio_smith.tts.base import Capabilities, PcmAudio, SynthParams, VoiceRef, to_float32
from audio_smith.tts.rate import apply_rate

DEFAULT_VOICE = "default"
MAX_CHARS = 400
FALLBACK_SR = 24_000
INSTALL_HINT = 'uv tool install "mr-audio-smith[chatterbox]"'


def _pick_device() -> str:
    """Choose cuda, then mps, then cpu; torch is only touched when the model is loaded."""
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class ChatterboxBackend:
    id = "chatterbox"
    model = "ResembleAI/chatterbox"

    def __init__(self, device: str | None = None) -> None:
        self._device = device
        self._model: Any = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "ChatterboxBackend":
        del settings
        return cls()

    def capabilities(self) -> Capabilities:
        return Capabilities(
            languages=["en"],
            cloning=True,
            builtin_voices=[DEFAULT_VOICE],
            sample_rate=FALLBACK_SR,
            max_chars=MAX_CHARS,
            streaming=False,
            license="MIT",
            commercial_ok=True,
        )

    def preflight(self) -> list[PreflightIssue]:
        try:
            import chatterbox  # noqa: F401, PLC0415
        except ImportError:
            return [
                PreflightIssue(
                    severity="error",
                    code="chatterbox_missing",
                    message="The chatterbox package is not installed",
                    hint=INSTALL_HINT,
                )
            ]
        return []

    def _load(self) -> Any:
        if self._model is None:
            try:
                from chatterbox.tts import ChatterboxTTS  # noqa: PLC0415
            except ImportError as exc:
                raise SynthesisError("The chatterbox package is not installed", hint=INSTALL_HINT) from exc
            self._model = ChatterboxTTS.from_pretrained(device=self._device or _pick_device())
        return self._model

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        kwargs: dict[str, str] = {}
        if not voice.builtin:
            from audio_smith.voices.consent import require_consent  # noqa: PLC0415

            require_consent(voice)
            if voice.reference_wav is None:
                raise UsageError(
                    f"Voice {voice.id!r} has no reference clip", hint="Register the voice again."
                )
            kwargs["audio_prompt_path"] = str(voice.reference_wav)
        model = self._load()
        wav = model.generate(text, **kwargs)
        samples = to_float32(np.asarray(wav.squeeze().cpu().numpy()))
        pcm = PcmAudio(samples=samples, sample_rate=int(model.sr))
        # Chatterbox has no native speed control, so rate is applied after synthesis (as for Maya 2).
        return apply_rate(pcm, params.rate) if params.rate != 1.0 else pcm
