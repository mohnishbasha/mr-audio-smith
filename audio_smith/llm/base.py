"""LLM provider protocol, shared HTTP helpers, and the think-block stripper.

Why: every provider must look identical to the script writer, so the contract and the
retry behaviour live in one place instead of being re-implemented per provider.
"""

import ipaddress
import re
import time
from typing import Protocol
from urllib.parse import urlparse

import httpx

from audio_smith.errors import LLMError
from audio_smith.preflight import PreflightIssue

__all__ = ["LLMError", "LLMProvider", "is_local_host", "post_json", "strip_think"]

HTTP_TIMEOUT_S = 300.0
PROBE_TIMEOUT_S = 5.0
MAX_RETRIES = 2
BACKOFF_BASE_S = 0.5
SERVER_ERROR_MIN = 500
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
LOCAL_NAMES = frozenset({"localhost", "host.docker.internal"})


class LLMProvider(Protocol):
    """A text completion backend. preflight() never raises; complete() raises LLMError."""

    id: str

    def preflight(self) -> list[PreflightIssue]: ...

    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str: ...


def strip_think(text: str) -> str:
    """Remove reasoning blocks so they never leak into a narration script."""
    return THINK_RE.sub("", text).strip()


def is_local_host(url: str) -> bool:
    """True when the URL points at this machine or a private network (no data leaves)."""
    host = urlparse(url).hostname or ""
    if host in LOCAL_NAMES or host.endswith(".local"):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback


def post_json(
    client: httpx.Client, url: str, payload: dict[str, object], headers: dict[str, str] | None = None
) -> dict[str, object]:
    """POST JSON with retries on connection errors and 5xx; raise LLMError otherwise.

    Why: local servers restart or warm up models, so a short backoff avoids failing a run
    on a transient blip. 4xx is a caller bug and is never retried.
    """
    last = "no attempt made"
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            time.sleep(BACKOFF_BASE_S * 2 ** (attempt - 1))
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT_S)
        except httpx.TransportError as e:
            last = f"connection error: {type(e).__name__}"
            continue
        if resp.status_code >= SERVER_ERROR_MIN:
            last = f"HTTP {resp.status_code}"
            continue
        if resp.status_code >= 400:
            raise LLMError(f"LLM request rejected: HTTP {resp.status_code}", hint=_snippet(resp))
        body = _json_object(resp)
        if body is not None:
            return body
        raise LLMError("LLM reply was not a JSON object", hint=f"POST {url}")
    raise LLMError(f"LLM request failed after retries: {last}", hint=f"Check that {url} is reachable.")


def _snippet(resp: httpx.Response) -> str:
    return resp.text[:200]


def _json_object(resp: httpx.Response) -> dict[str, object] | None:
    try:
        data: object = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
