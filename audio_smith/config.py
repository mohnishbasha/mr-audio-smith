"""Settings with documented precedence: CLI overrides > environment > audio-smith.toml > defaults.

The project file is discovered by walking upward from the working directory. Unknown keys and
secret-looking keys in the file produce warnings instead of failures, so a config written for a
newer version still loads and secrets never live in a committed file.
"""

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from audio_smith.errors import UsageError

PROJECT_FILE = "audio-smith.toml"
SECRET_KEY_RE = re.compile(r"(key|token|secret)", re.IGNORECASE)
REDACTED = "***"
DEFAULT_MAX_FETCH_BYTES = 5 * 1024 * 1024


class Settings(BaseSettings):
    """All runtime configuration. Secrets are SecretStr and only come from the environment."""

    model_config = SettingsConfigDict(env_prefix="AUDIO_SMITH_", extra="ignore", populate_by_name=True)

    env: Literal["dev", "stage", "prod"] = "prod"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["pretty", "json"] = "pretty"
    cache_dir: Path = Path("~/.cache/audio-smith")
    out_dir: Path = Path("./audio")
    voices_dir: Path = Path("~/.config/audio-smith/voices")
    profiles_dir: Path = Path("./profiles")
    default_profile: str = "kid-5"
    default_voice: str | None = None
    default_backend: str = "maya2"
    maya2_url: str = "http://127.0.0.1:8080/v1"
    maya2_mode: Literal["http", "inproc"] = "http"
    openai_compat_url: str = "http://127.0.0.1:8000/v1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    llm: str = "ollama:qwen3:14b"
    ollama_host: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("AUDIO_SMITH_OLLAMA_HOST", "OLLAMA_HOST", "ollama_host"),
    )
    server_host: str = "127.0.0.1"
    server_port: int = 7340
    server_token: SecretStr | None = None
    server_rate_limit_per_hour: int = 30
    studio_port: int = 7341
    qa_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    takes_per_chunk: int = Field(default=2, ge=1, le=10)
    synth_concurrency: int = Field(default=2, ge=1, le=16)
    max_fetch_bytes: int = DEFAULT_MAX_FETCH_BYTES
    fetch_timeout_s: float = 20.0
    allow_private: bool = False
    accept_noncommercial: bool = False
    embed_label: str = "Listen"
    embed_size: Literal["default", "kid"] = "default"
    embed_media_base: str = ""
    embed_script_mode: Literal["self", "jsdelivr"] = "self"
    embed_script_path: str = "/media/audio/audio-smith-player.js"
    config_warnings: list[str] = Field(default_factory=list, exclude=True)

    def resolved(self, path: Path) -> Path:
        """Expand ~ so every consumer sees an absolute-ish path."""
        return path.expanduser()

    def redacted(self) -> dict[str, Any]:
        """Dump for display or logs with every secret-looking value masked."""
        data = self.model_dump(mode="json")
        return {k: (REDACTED if SECRET_KEY_RE.search(k) and v is not None else v) for k, v in data.items()}


def find_project_file(start: Path | None = None) -> Path | None:
    """Walk upward from start (default cwd) and return the first audio-smith.toml."""
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        f = candidate / PROJECT_FILE
        if f.is_file():
            return f
    return None


def _read_file(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise UsageError(f"Cannot read {path}: {e}", hint="Fix the TOML syntax in the project file.") from e
    known = set(Settings.model_fields) - {"config_warnings"}
    data: dict[str, Any] = {}
    warnings: list[str] = []
    for key, value in raw.items():
        if SECRET_KEY_RE.search(key):
            warnings.append(f"{path}: ignoring secret-looking key '{key}'; set it in the environment instead")
        elif key not in known:
            warnings.append(f"{path}: unknown key '{key}' ignored")
        else:
            data[key] = value
    return data, warnings


def load_settings(
    overrides: Mapping[str, Any] | None = None,
    config_path: Path | None = None,
) -> Settings:
    """Build Settings honoring the precedence order. None-valued overrides are ignored."""
    path = config_path or find_project_file()
    file_data, warnings = _read_file(path) if path else ({}, [])
    from_env = Settings()
    env_data = {k: getattr(from_env, k) for k in from_env.model_fields_set}
    cli_data = {k: v for k, v in (overrides or {}).items() if v is not None}
    merged = {**file_data, **env_data, **cli_data, "config_warnings": warnings}
    return Settings(**merged)
