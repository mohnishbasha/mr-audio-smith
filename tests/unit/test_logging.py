import json
from collections.abc import Iterator

import pytest
import structlog
from pydantic import SecretStr

from audio_smith.config import REDACTED
from audio_smith.logging import build_processors, configure_logging, get_logger, redact_secrets


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def _redact(event: dict[str, object]) -> dict[str, object]:
    return dict(redact_secrets(None, "info", dict(event)))


@pytest.mark.parametrize(
    "name", ["api_key", "OPENAI_API_KEY", "server_token", "Authorization_Token", "client_secret"]
)
def test_logging_redacts_secret_named_keys(name: str) -> None:
    assert _redact({"event": "x", name: "hunter2"})[name] == REDACTED


def test_logging_redacts_nested_and_listed_values_and_secretstr() -> None:
    out = _redact(
        {
            "event": "x",
            "cfg": {"llm": {"api_key": "a"}, "port": 1},
            "rows": [{"token": "b"}, "plain"],
            "wrapped": SecretStr("c"),
        }
    )
    assert out["cfg"] == {"llm": {"api_key": REDACTED}, "port": 1}
    assert out["rows"] == [{"token": REDACTED}, "plain"]
    assert out["wrapped"] == REDACTED


def test_logging_leaves_innocent_values_alone() -> None:
    assert _redact({"event": "fetch", "url": "https://x.test", "bytes": 3}) == {
        "event": "fetch",
        "url": "https://x.test",
        "bytes": 3,
    }


def test_logging_deeply_nested_input_is_bounded() -> None:
    deep: dict[str, object] = {"leaf": "x"}
    for _ in range(50):
        deep = {"n": deep}
    assert "<max depth>" in json.dumps(_redact({"event": "x", "deep": deep}))


def test_logging_json_format_goes_to_stderr_and_redacts(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json", "info")
    get_logger().info("call", api_key="sk-live-123", step=2)
    captured = capsys.readouterr()
    assert captured.out == ""
    record = json.loads(captured.err)
    assert record["api_key"] == REDACTED and record["step"] == 2
    assert record["event"] == "call" and record["level"] == "info" and "timestamp" in record
    assert "sk-live-123" not in captured.err


def test_logging_pretty_format_redacts_and_respects_level(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("pretty", "warning")
    log = get_logger()
    log.info("hidden")
    log.warning("shown", server_token="tok-999")
    err = capsys.readouterr().err
    assert "hidden" not in err and "shown" in err
    assert "tok-999" not in err and REDACTED in err


def test_logging_exception_text_does_not_leak_through_redacted_keys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json", "info")
    get_logger().error("failed", secret="s3cr3t")
    assert "s3cr3t" not in capsys.readouterr().err


def test_logging_redaction_runs_before_renderer() -> None:
    names = [getattr(p, "__name__", type(p).__name__) for p in build_processors("json")]
    assert names.index("redact_secrets") < names.index("JSONRenderer")
