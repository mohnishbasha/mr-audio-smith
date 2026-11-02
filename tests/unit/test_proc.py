import subprocess
import sys

import pytest

from audio_smith import proc


def test_proc_run_returns_stdout() -> None:
    assert proc.run([sys.executable, "-c", "print('hi')"]).strip() == b"hi"


def test_proc_run_rejects_shell_string() -> None:
    with pytest.raises(TypeError):
        proc.run("echo hi")  # type: ignore[arg-type]  # deliberately wrong type


def test_proc_run_nonzero_raises() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        proc.run([sys.executable, "-c", "import sys; sys.exit(3)"])
