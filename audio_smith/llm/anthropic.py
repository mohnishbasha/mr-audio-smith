"""Anthropic provider via the official SDK (optional `cloud` extra, imported lazily)."""

import importlib
import os
from typing import Any

from audio_smith.llm.base import LLMError, strip_think
from audio_smith.preflight import PreflightIssue

API_KEY_ENV = "ANTHROPIC_API_KEY"
INSTALL_HINT = 'uv tool install "mr-audio-smith[cloud]"'


def _load_sdk() -> Any | None:
    """Import the SDK at the third-party boundary; None when the extra is not installed."""
    try:
        return importlib.import_module("anthropic")
    except ImportError:
        return None


class AnthropicProvider:
    """Messages API. The key comes from ANTHROPIC_API_KEY only and is never logged."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.id = f"anthropic/{model}"

    def preflight(self) -> list[PreflightIssue]:
        if _load_sdk() is None:
            return [
                PreflightIssue(
                    severity="error",
                    code="anthropic.sdk_missing",
                    message="The anthropic package is not installed",
                    hint=INSTALL_HINT,
                )
            ]
        issues = [
            PreflightIssue(
                severity="warning",
                code="llm.cloud_active",
                message="cloud provider active: prompts are sent to Anthropic",
            )
        ]
        if not os.environ.get(API_KEY_ENV):
            issues.append(
                PreflightIssue(
                    severity="error",
                    code="anthropic.key_missing",
                    message=f"{API_KEY_ENV} is not set",
                    hint=f"export {API_KEY_ENV}=... in your environment.",
                )
            )
        return issues

    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str:
        """Call messages.create. `seed` is unsupported by the API and ignored."""
        sdk = _load_sdk()
        if sdk is None:
            raise LLMError("The anthropic package is not installed", hint=INSTALL_HINT)
        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise LLMError(f"{API_KEY_ENV} is not set", hint=f"export {API_KEY_ENV}=...")
        try:
            msg = sdk.Anthropic(api_key=key).messages.create(
                model=self.model,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            raise LLMError(f"Anthropic request failed: {type(e).__name__}") from e
        return strip_think("".join(str(b.text) for b in msg.content if getattr(b, "type", "") == "text"))
