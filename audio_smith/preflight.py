"""Preflight issue model shared by TTS backends, LLM providers, and doctor."""

from typing import Literal

from pydantic import BaseModel

Severity = Literal["error", "warning", "info"]


class PreflightIssue(BaseModel):
    """One problem found before a run. preflight() returns these and never raises."""

    severity: Severity
    code: str
    message: str
    hint: str | None = None


def has_errors(issues: list[PreflightIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
