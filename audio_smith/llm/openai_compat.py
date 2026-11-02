"""OpenAI-compatible chat provider (vLLM, LM Studio, llama.cpp server, hosted APIs)."""

import os

import httpx

from audio_smith.llm.base import PROBE_TIMEOUT_S, LLMError, is_local_host, post_json, strip_think
from audio_smith.preflight import PreflightIssue

API_KEY_ENV = "OPENAI_API_KEY"


class OpenAICompatProvider:
    """Chat completions via POST {base_url}/chat/completions."""

    def __init__(self, base_url: str, model: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.id = f"openai_compat/{model}"
        self._client = client or httpx.Client()

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(API_KEY_ENV)
        return {"Authorization": f"Bearer {key}"} if key else {}

    def preflight(self) -> list[PreflightIssue]:
        issues: list[PreflightIssue] = []
        try:
            resp = self._client.get(
                f"{self.base_url}/models", headers=self._headers(), timeout=PROBE_TIMEOUT_S
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            issues.append(
                PreflightIssue(
                    severity="error",
                    code="openai_compat.unreachable",
                    message=f"LLM endpoint is not reachable at {self.base_url}",
                    hint="Start the server or fix the base URL in --llm openai_compat:<url>#<model>.",
                )
            )
        if not is_local_host(self.base_url):
            issues.append(
                PreflightIssue(
                    severity="warning",
                    code="llm.cloud_active",
                    message="cloud provider active: prompts are sent to a remote host",
                )
            )
        return issues

    def complete(
        self, system: str, user: str, *, temperature: float, seed: int | None, max_tokens: int
    ) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            payload["seed"] = seed
        body = post_json(self._client, f"{self.base_url}/chat/completions", payload, self._headers())
        return strip_think(_first_content(body))


def _first_content(body: dict[str, object]) -> str:
    choices = body.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMError("LLM reply had no choices[0].message.content")
    return content
