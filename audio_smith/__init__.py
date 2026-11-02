"""mr-audio-smith: turn any web page into an audience-tuned narration."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mr-audio-smith")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
