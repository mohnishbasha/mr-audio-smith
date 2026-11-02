"""Filesystem safety: slugs from URLs, writes confined to an output root, atomic replace."""

import os
import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from audio_smith.errors import UsageError

SLUG_MAX = 80
_SLUG_BAD = re.compile(r"[^a-z0-9-]+")


def safe_slug(source: str) -> str:
    """Derive a filesystem-safe slug from a URL path stem or file name.

    Only [a-z0-9-] survive, so traversal sequences, separators, and dots cannot appear.
    """
    parsed = urlparse(source)
    path = unquote(parsed.path if parsed.scheme in ("http", "https", "file") else source)
    stem = Path(path.rstrip("/")).stem or parsed.netloc or "page"
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    slug = _SLUG_BAD.sub("-", ascii_stem.lower()).strip("-")[:SLUG_MAX].strip("-")
    return slug or "page"


def ensure_inside(root: Path, candidate: Path) -> Path:
    """Resolve candidate and refuse it unless it is inside root."""
    root_r = root.resolve()
    cand_r = candidate.resolve()
    if cand_r != root_r and root_r not in cand_r.parents:
        raise UsageError(
            f"Refusing to write outside {root_r}: {cand_r}", hint="Use a path inside the output dir."
        )
    return cand_r


def atomic_write(path: Path, data: bytes | str, *, mode: int | None = None) -> Path:
    """Write to a temp file in the same directory, fsync, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            Path(tmp).chmod(mode)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
