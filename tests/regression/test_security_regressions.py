"""Security regressions: each test pins a gap found in the Sprint 6 review (docs/SECURITY_REVIEW.md)."""

import json
import os
import subprocess
import sys

from audio_smith.config import REDACTED


def regression_logs_redact_secret_named_keys_in_json_output() -> None:
    """The review found structlog as a dependency but no redaction processor; secrets could be logged."""
    code = (
        "from audio_smith.logging import configure_logging, get_logger;"
        "configure_logging('json');"
        "get_logger().info('x', openai_api_key='sk-test-1234', nested={'client_secret': 'abc'})"
    )
    env = {**os.environ, "PYTHONUTF8": "1"}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env)
    assert "sk-test-1234" not in result.stderr and "abc" not in result.stderr
    assert json.loads(result.stderr)["openai_api_key"] == REDACTED
