"""mr-audio-smith: turn any web page into an audience-tuned narration."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mr-audio-smith")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__", "narrate"]


def __getattr__(name: str) -> object:
    """`audio_smith.narrate(...)` without importing the whole pipeline at package import time."""
    if name == "narrate":
        from audio_smith.api import narrate  # noqa: PLC0415

        return narrate
    raise AttributeError(name)
