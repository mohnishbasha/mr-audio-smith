"""Structured logging with secret redaction (BUILD_PROMPT "Secrets", ARCHITECTURE section 9).

Every event passes through `redact_secrets` before rendering, so a value whose key contains
`key`, `token`, or `secret` (any case) is replaced by `***`, however deeply it is nested and
whichever renderer (pretty or JSON) is active. Logs go to stderr so stdout stays machine
readable. Nothing here sends data anywhere: there is no telemetry.
"""

import re
import sys
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, Literal

import structlog
from pydantic import SecretBytes, SecretStr

from audio_smith.config import REDACTED

LogFormat = Literal["pretty", "json"]
LOG_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
SECRET_NAME_RE = re.compile(r"(key|token|secret)", re.IGNORECASE)
MAX_DEPTH = 8
DEPTH_EXCEEDED = "<max depth>"
_SECRET_TYPES = (SecretStr, SecretBytes)


def _redact(value: Any, depth: int) -> Any:
    """Return a copy of value with secret-named mapping entries masked."""
    if depth > MAX_DEPTH:
        return DEPTH_EXCEEDED
    if isinstance(value, _SECRET_TYPES):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: REDACTED if SECRET_NAME_RE.search(str(k)) else _redact(v, depth + 1) for k, v in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_redact(v, depth + 1) for v in value]
    return value


def redact_secrets(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: mask values of keys matching `*key*`, `*token*`, `*secret*`."""
    redacted = _redact(dict(event_dict), 0)
    event_dict.clear()
    event_dict.update(redacted)
    return event_dict


def build_processors(log_format: LogFormat) -> list[Any]:
    """The processor chain: context, level, timestamp, redaction, then the renderer."""
    renderer: Any = (
        structlog.processors.JSONRenderer(sort_keys=True)
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        redact_secrets,
        renderer,
    ]


def configure_logging(log_format: LogFormat = "pretty", log_level: str = "info") -> None:
    """Configure structlog for the process: stderr output, redaction always on."""
    structlog.configure(
        processors=build_processors(log_format),
        wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVELS.get(log_level, LOG_LEVELS["info"])),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "audio_smith") -> Any:
    """A bound logger; call `configure_logging` once at the front door first."""
    return structlog.get_logger(name)
