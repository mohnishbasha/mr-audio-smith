"""Backend registry: ids to factories. Heavy imports happen inside factories only."""

from collections.abc import Callable

from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.tts.base import TTSBackend

BACKEND_IDS = ("maya2", "kokoro", "chatterbox", "openai", "openai_compat", "mock")


def _maya2(s: Settings) -> TTSBackend:
    from audio_smith.tts.maya2 import Maya2Backend  # noqa: PLC0415 - lazy by design

    return Maya2Backend.from_settings(s)


def _kokoro(s: Settings) -> TTSBackend:
    from audio_smith.tts.kokoro import KokoroBackend  # noqa: PLC0415

    return KokoroBackend.from_settings(s)


def _chatterbox(s: Settings) -> TTSBackend:
    from audio_smith.tts.chatterbox import ChatterboxBackend  # noqa: PLC0415

    return ChatterboxBackend.from_settings(s)


def _openai(s: Settings) -> TTSBackend:
    from audio_smith.tts.openai_compat import OpenAICompatBackend  # noqa: PLC0415

    return OpenAICompatBackend.cloud(s)


def _openai_compat(s: Settings) -> TTSBackend:
    from audio_smith.tts.openai_compat import OpenAICompatBackend  # noqa: PLC0415

    return OpenAICompatBackend.compat(s)


def _mock(_: Settings) -> TTSBackend:
    from audio_smith.tts.mock import MockBackend  # noqa: PLC0415

    return MockBackend()


FACTORIES: dict[str, Callable[[Settings], TTSBackend]] = {
    "maya2": _maya2,
    "kokoro": _kokoro,
    "chatterbox": _chatterbox,
    "openai": _openai,
    "openai_compat": _openai_compat,
    "mock": _mock,
}


def get_backend(backend_id: str, settings: Settings) -> TTSBackend:
    if backend_id not in FACTORIES:
        raise UsageError(f"Unknown TTS backend {backend_id!r}", hint=f"Known: {', '.join(BACKEND_IDS)}")
    return FACTORIES[backend_id](settings)
