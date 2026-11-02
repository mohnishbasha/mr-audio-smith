"""The only place that starts subprocesses: argument arrays, no shell, always a timeout."""

import subprocess
from collections.abc import Sequence

DEFAULT_TIMEOUT_S = 600.0


def run(
    args: Sequence[str], *, timeout: float = DEFAULT_TIMEOUT_S, input_bytes: bytes | None = None
) -> bytes:
    """Run a command and return stdout. Raises CalledProcessError or TimeoutExpired."""
    if isinstance(args, str):
        raise TypeError("pass an argument list, never a shell string")
    result = subprocess.run(  # noqa: S603 - argument array, shell=False, bounded by timeout
        list(args), check=True, capture_output=True, timeout=timeout, input=input_bytes
    )
    return result.stdout


def run_capture(args: Sequence[str], *, timeout: float = DEFAULT_TIMEOUT_S) -> tuple[bytes, bytes]:
    """Run a command and return (stdout, stderr).

    Why: ffmpeg prints loudness measurements and progress to stderr, so callers that parse them
    need both streams. Same rules as `run`: argument list only, no shell, bounded by a timeout.
    Raises CalledProcessError (with stderr attached) or TimeoutExpired.
    """
    if isinstance(args, str):
        raise TypeError("pass an argument list, never a shell string")
    result = subprocess.run(  # noqa: S603 - argument array, shell=False, bounded by timeout
        list(args), check=True, capture_output=True, timeout=timeout
    )
    return result.stdout, result.stderr


def run_interactive(args: Sequence[str]) -> None:
    """Run an interactive program (the author's editor) attached to the terminal; no shell."""
    if isinstance(args, str):
        raise TypeError("pass an argument list, never a shell string")
    subprocess.run(list(args), check=True)  # noqa: S603 - argument array chosen by the user ($EDITOR)
