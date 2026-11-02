from pathlib import Path

import pytest

from audio_smith.config import Settings, find_project_file, load_settings


def test_config_defaults_when_nothing_set(tmp_path: Path) -> None:
    s = load_settings()
    assert s.default_backend == "maya2"
    assert s.maya2_url == "http://127.0.0.1:8080/v1"
    assert s.qa_threshold == 0.75
    assert s.max_fetch_bytes == 5 * 1024 * 1024


def test_config_file_overrides_defaults(tmp_path: Path) -> None:
    (tmp_path / "audio-smith.toml").write_text(
        'default_backend = "kokoro"\nqa_threshold = 0.8\n', encoding="utf-8"
    )
    s = load_settings()
    assert s.default_backend == "kokoro"
    assert s.qa_threshold == 0.8


def test_config_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "audio-smith.toml").write_text('default_backend = "kokoro"\n', encoding="utf-8")
    monkeypatch.setenv("AUDIO_SMITH_DEFAULT_BACKEND", "mock")
    assert load_settings().default_backend == "mock"


def test_config_cli_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_SMITH_DEFAULT_BACKEND", "mock")
    assert load_settings(overrides={"default_backend": "openai"}).default_backend == "openai"


def test_config_cli_none_override_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_SMITH_DEFAULT_BACKEND", "mock")
    assert load_settings(overrides={"default_backend": None}).default_backend == "mock"


def test_config_audio_smith_toml_discovered_upward_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "audio-smith.toml").write_text('default_backend = "kokoro"\n', encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert find_project_file() == tmp_path / "audio-smith.toml"
    assert load_settings().default_backend == "kokoro"


def test_config_unknown_key_warns_not_crashes(tmp_path: Path) -> None:
    (tmp_path / "audio-smith.toml").write_text(
        'nonsense_key = 1\ndefault_backend = "mock"\n', encoding="utf-8"
    )
    s = load_settings()
    assert s.default_backend == "mock"
    assert any("nonsense_key" in w for w in s.config_warnings)


def test_config_secret_keys_in_file_ignored_with_warning(tmp_path: Path) -> None:
    (tmp_path / "audio-smith.toml").write_text('server_token = "abc"\n', encoding="utf-8")
    s = load_settings()
    assert s.server_token is None
    assert any("server_token" in w for w in s.config_warnings)


def test_config_invalid_toml_raises_usage_error(tmp_path: Path) -> None:
    from audio_smith.errors import UsageError

    (tmp_path / "audio-smith.toml").write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(UsageError):
        load_settings()


def test_config_explicit_config_path(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere.toml"
    other.write_text('default_backend = "kokoro"\n', encoding="utf-8")
    assert load_settings(config_path=other).default_backend == "kokoro"


def test_config_redacted_dump_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_SMITH_SERVER_TOKEN", "supersecret")
    dumped = load_settings().redacted()
    assert dumped["server_token"] == "***"


def test_config_settings_is_pydantic_model() -> None:
    assert isinstance(Settings(), Settings)


def test_config_precedence_flags_over_env_over_file_over_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "audio-smith.toml").write_text(
        'default_backend = "kokoro"\nllm = "fake"\nqa_threshold = 0.9\n'
    )
    monkeypatch.setenv("AUDIO_SMITH_DEFAULT_BACKEND", "mock")
    monkeypatch.setenv("AUDIO_SMITH_LLM", "ollama:qwen3:0.6b")
    s = load_settings(overrides={"default_backend": "openai"})
    assert s.default_backend == "openai"  # flag beats env
    assert s.llm == "ollama:qwen3:0.6b"  # env beats file
    assert s.qa_threshold == 0.9  # file beats default
    assert s.server_port == 7340  # default


def test_config_env_prefix_audio_smith(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_BACKEND", "kokoro")
    monkeypatch.setenv("AUDIO_SMITH_SERVER_PORT", "9999")
    s = load_settings()
    assert s.default_backend == "maya2"
    assert s.server_port == 9999


def test_config_ollama_host_standard_env_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
    assert load_settings().ollama_host == "http://ollama:11434"
