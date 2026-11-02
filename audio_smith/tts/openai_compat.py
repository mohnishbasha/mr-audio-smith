"""OpenAI-compatible speech backend (ARCHITECTURE 6.5, FR-010).

One adapter serves OpenAI cloud and any local server that mimics /v1/audio/speech. Model
quirks live in three overridable hooks (map_voice, map_params, map_text) so subclasses such
as the Maya 2 adapter stay small. Retries are implemented here, not in the SDK, so tests
control backoff.
"""

import io
import ipaddress
import os
import random
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
import openai
import soundfile as sf

from audio_smith.config import Settings
from audio_smith.errors import SynthesisError
from audio_smith.preflight import PreflightIssue
from audio_smith.tts.base import Capabilities, PcmAudio, SynthParams, VoiceRef, to_float32

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_KEY_ENV = "OPENAI_API_KEY"
OPENAI_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
]
OPENAI_LANGUAGES = ["en", "hi", "mr", "ta", "te", "bn", "gu", "kn", "ml", "pa", "or", "as"]
OPENAI_SAMPLE_RATE = 24_000
OPENAI_MAX_CHARS = 4000
PLACEHOLDER_KEY = "not-needed"
DEFAULT_TIMEOUT_S = 60.0
PREFLIGHT_TIMEOUT_S = 5.0
MAX_RETRIES = 2
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 8.0
RETRY_AFTER_CAP_S = 30.0
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
HTTP_SERVER_ERROR = 500
EMPHASIS_RE = re.compile(r"\*(\S(?:[^*]*?\S)?)\*")
LOCAL_HOSTS = frozenset({"localhost", "host.docker.internal"})


def is_local_host(url: str) -> bool:
    """True for localhost, loopback, and private-range hosts (no data leaves the machine)."""
    host = urlparse(url).hostname or ""
    if host in LOCAL_HOSTS or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


class OpenAICompatBackend:
    """TTSBackend over the OpenAI SDK with its own bounded retry loop."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        backend_id: str,
        capabilities: Capabilities,
        client: openai.OpenAI | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        sleep: Callable[[float], None] = time.sleep,
        require_key: bool = False,
    ) -> None:
        self.id = backend_id
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._caps = capabilities
        self._api_key = api_key
        self._require_key = require_key
        self._sleep = sleep
        self._client = client or openai.OpenAI(
            base_url=self.base_url, api_key=api_key or PLACEHOLDER_KEY, timeout=timeout, max_retries=0
        )

    @classmethod
    def cloud(cls, settings: Settings) -> "OpenAICompatBackend":
        caps = Capabilities(
            languages=OPENAI_LANGUAGES,
            cloning=False,
            builtin_voices=OPENAI_VOICES,
            sample_rate=OPENAI_SAMPLE_RATE,
            max_chars=OPENAI_MAX_CHARS,
            streaming=False,
            license="OpenAI terms",
            commercial_ok=True,
        )
        return cls(
            base_url=OPENAI_BASE_URL,
            api_key=os.environ.get(OPENAI_KEY_ENV),
            model=settings.openai_tts_model,
            backend_id="openai",
            capabilities=caps,
            require_key=True,
        )

    @classmethod
    def compat(cls, settings: Settings) -> "OpenAICompatBackend":
        caps = Capabilities(
            languages=OPENAI_LANGUAGES,
            cloning=False,
            builtin_voices=[],
            sample_rate=OPENAI_SAMPLE_RATE,
            max_chars=OPENAI_MAX_CHARS,
            streaming=False,
            license="depends on the server model",
            commercial_ok=True,
        )
        return cls(
            base_url=settings.openai_compat_url,
            api_key=os.environ.get(OPENAI_KEY_ENV),
            model=settings.openai_tts_model,
            backend_id="openai_compat",
            capabilities=caps,
        )

    def capabilities(self) -> Capabilities:
        return self._caps

    # Adapter hooks ---------------------------------------------------------------------

    def map_voice(self, voice: VoiceRef) -> str:
        """Server-side voice name for a VoiceRef (override to register clones)."""
        return voice.id

    def map_params(self, params: SynthParams) -> dict[str, Any]:
        """Extra request-body fields; plain OpenAI servers only understand `speed`."""
        return {} if params.rate == 1.0 else {"speed": params.rate}

    def map_text(self, text: str) -> str:
        """Strip `*word*` emphasis: no OpenAI-style server understands it."""
        return EMPHASIS_RE.sub(r"\1", text)

    # Synthesis -------------------------------------------------------------------------

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        voice_name = self.map_voice(voice)
        body = self.map_params(params)
        data = self._request_with_retry(self.map_text(text), voice_name, body)
        return self._decode(data)

    def _request_with_retry(self, text: str, voice_name: str, body: dict[str, Any]) -> bytes:
        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._client.audio.speech.create(
                    model=self.model,
                    voice=voice_name,
                    input=text,
                    response_format="wav",
                    extra_body=body,
                )
                return bytes(resp.content)
            except openai.APIStatusError as e:
                if e.status_code not in TRANSIENT_STATUSES:
                    raise SynthesisError(
                        f"{self.id} rejected the request ({e.status_code}): {e.message}",
                        hint="Check the model, voice, and text; this error is not retried.",
                    ) from e
                last = e
            except openai.APIConnectionError as e:  # includes APITimeoutError
                last = e
            if attempt < MAX_RETRIES:
                self._sleep(self._delay(attempt, last))
        raise SynthesisError(
            f"{self.id} failed after {MAX_RETRIES + 1} attempts: {last}",
            hint="Run `mr-audio-smith doctor` and check the server is up and not overloaded.",
        ) from last

    @staticmethod
    def _delay(attempt: int, err: Exception | None) -> float:
        if isinstance(err, openai.APIStatusError):
            raw = err.response.headers.get("retry-after", "")
            if raw.isdigit():
                return min(float(raw), RETRY_AFTER_CAP_S)
        base = float(min(BACKOFF_BASE_S * 2**attempt, BACKOFF_CAP_S))
        jitter: float = 0.5 + random.random() / 2  # noqa: S311 - jitter, not security
        return base * jitter

    def _decode(self, data: bytes) -> PcmAudio:
        try:
            samples, sr = sf.read(io.BytesIO(data), dtype="float32")
        except Exception as e:
            raise SynthesisError(
                f"{self.id} returned audio that is not a valid WAV: {e}",
                hint="Check the server's response_format support.",
            ) from e
        return PcmAudio(samples=to_float32(samples), sample_rate=int(sr))

    # Preflight -------------------------------------------------------------------------

    def preflight(self) -> list[PreflightIssue]:
        issues: list[PreflightIssue] = []
        if self._require_key and not self._api_key:
            issues.append(
                PreflightIssue(
                    severity="error",
                    code="tts.openai_key_missing",
                    message=f"{OPENAI_KEY_ENV} is not set",
                    hint=f"export {OPENAI_KEY_ENV}=... or pick another backend.",
                )
            )
        issues.extend(self._reachability())
        if not is_local_host(self.base_url):
            issues.append(
                PreflightIssue(
                    severity="warning",
                    code="tts.cloud_active",
                    message=f"Script text is sent to {urlparse(self.base_url).hostname}",
                    hint="Use --backend maya2 or kokoro to keep text on this machine.",
                )
            )
        return issues

    def _reachability(self) -> list[PreflightIssue]:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=PREFLIGHT_TIMEOUT_S)
        except httpx.HTTPError as e:
            return [self._unreachable(str(e))]
        if resp.status_code >= HTTP_SERVER_ERROR:
            return [self._unreachable(f"HTTP {resp.status_code}")]
        return []

    def _unreachable(self, why: str) -> PreflightIssue:
        return PreflightIssue(
            severity="error",
            code="tts.unreachable",
            message=f"{self.id} at {self.base_url} is unreachable: {why}",
            hint="Check the URL (AUDIO_SMITH_OPENAI_COMPAT_URL) and network.",
        )
