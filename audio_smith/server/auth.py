"""Bearer-token auth, loopback rule, and the sliding-window rate limiter (NFR-005).

Tokens are compared in constant time and never logged or echoed in errors.
"""

import hashlib
import hmac
import ipaddress
import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from audio_smith.config import Settings
from audio_smith.errors import AudioSmithError, UsageError

WINDOW_S = 3600.0
BEARER_PREFIX = "bearer "
LOOPBACK_NAMES = frozenset({"localhost"})


class UnauthorizedError(AudioSmithError):
    code = "unauthorized"
    stage = "auth"
    http_status = 401


class NotFoundError(AudioSmithError):
    code = "not_found"
    stage = "server"
    http_status = 404


class RateLimitedError(AudioSmithError):
    code = "rate_limited"
    stage = "server"
    http_status = 429

    def __init__(self, message: str, *, retry_after: int, hint: str | None = None) -> None:
        super().__init__(message, hint=hint)
        self.retry_after = retry_after


class InvalidRequestError(AudioSmithError):
    code = "invalid_request"
    stage = "server"
    http_status = 422


def is_loopback(host: str) -> bool:
    """True for localhost, 127.0.0.0/8, and ::1; anything else (including 0.0.0.0) is not."""
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def configured_token(settings: Settings) -> bytes | None:
    """The bearer token as bytes, or None when unset or empty."""
    secret = settings.server_token.get_secret_value() if settings.server_token else ""
    return secret.encode() if secret else None


def require_safe_bind(settings: Settings) -> None:
    """Refuse a non-loopback bind without a token (UsageError, exit code 2)."""
    if not is_loopback(settings.server_host) and configured_token(settings) is None:
        raise UsageError(
            f"Refusing to bind {settings.server_host} without a token",
            hint="Set AUDIO_SMITH_SERVER_TOKEN, or bind 127.0.0.1.",
        )


def check_bearer(header: str | None, expected: bytes | None) -> None:
    """Raise UnauthorizedError unless auth is off or the header carries the right token."""
    if expected is None:
        return
    supplied = b""
    if header and header.lower().startswith(BEARER_PREFIX):
        supplied = header[len(BEARER_PREFIX) :].strip().encode()
    if not hmac.compare_digest(supplied, expected):
        raise UnauthorizedError(
            "Missing or invalid bearer token", hint="Send 'Authorization: Bearer <token>'."
        )


def client_key(header: str | None, client_host: str | None, expected: bytes | None) -> str:
    """Rate-limit identity: a hash of the token when auth is on, else the client address."""
    if expected is not None and header:
        return "t:" + hashlib.sha256(header.encode()).hexdigest()[:16]
    return "ip:" + (client_host or "unknown")


class SlidingWindowLimiter:
    """At most `limit` hits per key within `window_s`; thread safe, clock injectable."""

    def __init__(
        self, limit: int, window_s: float = WINDOW_S, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """Record one hit or raise RateLimitedError carrying Retry-After seconds."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                wait = max(1, math.ceil(hits[0] + self.window_s - now))
                raise RateLimitedError(
                    f"Rate limit of {self.limit} jobs per hour reached",
                    retry_after=wait,
                    hint="Wait for the Retry-After interval or raise AUDIO_SMITH_SERVER_RATE_LIMIT_PER_HOUR.",
                )
            hits.append(now)
