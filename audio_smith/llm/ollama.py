"""Ollama provider over the local REST API (no data leaves the machine)."""

import httpx

from audio_smith.llm.base import PROBE_TIMEOUT_S, LLMError, post_json, strip_think
from audio_smith.preflight import PreflightIssue

NO_THINK_MODEL_PREFIX = "qwen3"


class OllamaProvider:
    """Chat completions via POST {host}/api/chat."""

    def __init__(self, model: str, host: str, client: httpx.Client | None = None) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.id = f"ollama/{model}"
        self._client = client or httpx.Client()

    def preflight(self) -> list[PreflightIssue]:
        """Check the server answers and the model is pulled."""
        try:
            resp = self._client.get(f"{self.host}/api/tags", timeout=PROBE_TIMEOUT_S)
            resp.raise_for_status()
            names = _model_names(resp.json())
        except (httpx.HTTPError, ValueError):
            return [
                PreflightIssue(
                    severity="error",
                    code="ollama.unreachable",
                    message=f"Ollama is not reachable at {self.host}",
                    hint="Start it with `ollama serve` or set AUDIO_SMITH_OLLAMA_HOST.",
                )
            ]
        if not any(n == self.model or n.split(":")[0] == self.model for n in names):
            return [
                PreflightIssue(
                    severity="error",
                    code="ollama.model_missing",
                    message=f"Ollama model {self.model} is not pulled",
                    hint=f"Run `ollama pull {self.model}`.",
                )
            ]
        return []

    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str:
        options: dict[str, object] = {"temperature": temperature, "num_predict": max_tokens}
        if seed is not None:
            options["seed"] = seed
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": options,
        }
        if self.model.startswith(NO_THINK_MODEL_PREFIX):
            payload["think"] = False
        body = post_json(self._client, f"{self.host}/api/chat", payload)
        message = body.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LLMError("Ollama reply had no message content")
        return strip_think(content)


def _model_names(data: object) -> list[str]:
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return []
    return [str(m["name"]) for m in models if isinstance(m, dict) and "name" in m]
