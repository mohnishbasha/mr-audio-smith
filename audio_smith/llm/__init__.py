"""LLM providers selected by a provider string (ARCHITECTURE section 6.7)."""

from pathlib import Path
from typing import Literal, cast

import httpx
from pydantic import BaseModel

from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.llm.base import LLMError, LLMProvider

__all__ = ["LLMError", "LLMProvider", "ProviderSpec", "get_provider", "parse_provider", "provider_label"]

Kind = Literal["ollama", "anthropic", "openai_compat", "fake"]
KNOWN_KINDS = ("ollama", "anthropic", "openai_compat", "fake")
FORMAT_HELP = "Use ollama:<model>, anthropic:<model-id>, openai_compat:<base_url>#<model>, or fake[:<dir>]."


class ProviderSpec(BaseModel):
    """Parsed provider string. For `fake`, `model` holds the optional fixture dir."""

    kind: Kind
    model: str = ""
    base_url: str | None = None


def parse_provider(spec: str) -> ProviderSpec:
    """Parse a provider string; raise UsageError listing known kinds when invalid."""
    kind, _, rest = spec.partition(":")
    if kind not in KNOWN_KINDS:
        raise UsageError(f"Unknown LLM provider {kind!r}; known: {', '.join(KNOWN_KINDS)}", hint=FORMAT_HELP)
    if kind == "fake":
        return ProviderSpec(kind="fake", model=rest)
    if not rest:
        raise UsageError(f"Provider {kind} needs a model", hint=FORMAT_HELP)
    if kind == "openai_compat":
        url, sep, model = rest.rpartition("#")
        if not sep or not url or not model:
            raise UsageError("openai_compat needs <base_url>#<model>", hint=FORMAT_HELP)
        return ProviderSpec(kind="openai_compat", model=model, base_url=url)
    return ProviderSpec(kind=cast(Kind, kind), model=rest)


def provider_label(spec: str) -> str:
    """`provider/model` for manifests; the base URL (which may embed credentials) is dropped."""
    parsed = parse_provider(spec)
    return f"{parsed.kind}/{parsed.model}" if parsed.model else parsed.kind


def get_provider(spec: str, settings: Settings, *, client: httpx.Client | None = None) -> LLMProvider:
    """Build the provider; imports are lazy so unused SDKs are never loaded."""
    parsed = parse_provider(spec)
    if parsed.kind == "ollama":
        from audio_smith.llm.ollama import OllamaProvider  # noqa: PLC0415

        return OllamaProvider(parsed.model, settings.ollama_host, client)
    if parsed.kind == "anthropic":
        from audio_smith.llm.anthropic import AnthropicProvider  # noqa: PLC0415

        return AnthropicProvider(parsed.model)
    if parsed.kind == "openai_compat":
        from audio_smith.llm.openai_compat import OpenAICompatProvider  # noqa: PLC0415

        return OpenAICompatProvider(parsed.base_url or "", parsed.model, client)
    from audio_smith.llm.fake import FakeProvider  # noqa: PLC0415

    return FakeProvider(Path(parsed.model) if parsed.model else None)
