"""Typed errors. Every failure carries a code, a stage, and an actionable hint.

Front doors map these to exit codes (CLI) or RFC 9457 problem+json (server). Messages and
hints must never include secrets or consent statements.
"""

from typing import Any, ClassVar

PROBLEM_TYPE_BASE = "https://getaudiosmith.com/problems/"


class AudioSmithError(Exception):
    """Base error; unexpected failures are wrapped in this at the front door."""

    code: ClassVar[str] = "internal_error"
    stage: ClassVar[str] = "any"
    exit_code: ClassVar[int] = 1
    http_status: ClassVar[int] = 500

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def to_problem(self) -> dict[str, Any]:
        """Render as an RFC 9457 problem document."""
        return {
            "type": PROBLEM_TYPE_BASE + self.code,
            "title": self.code,
            "status": self.http_status,
            "detail": self.message,
            "hint": self.hint,
            "stage": self.stage,
        }


class UsageError(AudioSmithError):
    code = "usage"
    stage = "config"
    exit_code = 2
    http_status = 400


class PreflightError(AudioSmithError):
    code = "preflight_failed"
    stage = "preflight"
    exit_code = 3
    http_status = 503

    def __init__(self, message: str, *, hint: str | None = None, issues: list[Any] | None = None) -> None:
        super().__init__(message, hint=hint)
        self.issues = issues or []


class ExtractError(AudioSmithError):
    code = "extract_failed"
    stage = "extract"
    exit_code = 4
    http_status = 422


class FetchError(ExtractError):
    code = "fetch_failed"
    stage = "fetch"


class ScriptInvalidError(AudioSmithError):
    code = "script_invalid"
    stage = "script"
    exit_code = 5
    http_status = 422

    def __init__(self, message: str, *, hint: str | None = None, violations: list[str] | None = None) -> None:
        super().__init__(message, hint=hint)
        self.violations = violations or []


class LLMError(AudioSmithError):
    """An LLM provider call failed (network, HTTP status, malformed reply, missing fixture)."""

    code = "llm_failed"
    stage = "script"
    exit_code = 5
    http_status = 502


class SynthesisError(AudioSmithError):
    code = "synthesis_failed"
    stage = "synth"
    exit_code = 6
    http_status = 502

    def __init__(self, message: str, *, hint: str | None = None, retryable: bool = True) -> None:
        super().__init__(message, hint=hint)
        self.retryable = retryable


class MasteringError(AudioSmithError):
    code = "mastering_failed"
    stage = "master"
    exit_code = 7
    http_status = 500


class ConsentError(AudioSmithError):
    code = "consent_missing"
    stage = "voice"
    exit_code = 8
    http_status = 403
