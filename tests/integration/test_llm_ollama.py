import os

import httpx
import pytest

from audio_smith.config import Settings
from audio_smith.llm.ollama import OllamaProvider

MODEL_ENV = "AUDIO_SMITH_IT_OLLAMA_MODEL"
DEFAULT_MODEL = "qwen3:0.6b"


@pytest.mark.integration
def it_ollama_chat_tiny_model_returns_text() -> None:
    provider = OllamaProvider(os.environ.get(MODEL_ENV, DEFAULT_MODEL), Settings().ollama_host)
    try:
        issues = provider.preflight()
    except httpx.HTTPError:
        issues = []
    if any(i.severity == "error" for i in issues):
        pytest.skip(f"Ollama or model unavailable: {issues[0].message}")
    out = provider.complete("Reply briefly.", "Say hello.", temperature=0.0, seed=1, max_tokens=64)
    assert out.strip()
