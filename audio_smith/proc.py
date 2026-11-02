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
