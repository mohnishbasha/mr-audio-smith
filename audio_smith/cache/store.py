"""Filesystem cache: cache/v1/{kind}/{key}.{ext}, atomic writes, age-based pruning."""

import time
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from audio_smith.cache.keys import CACHE_FORMAT
from audio_smith.paths import atomic_write

KINDS = ("blocks", "scripts", "chunks", "tracks", "takes")


class CacheInfo(BaseModel):
    root: str
    entries: dict[str, int]
    bytes: int


class CacheStore:
    """A content-addressed store. Keys come from audio_smith.cache.keys only."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.base = self.root / CACHE_FORMAT

    def path(self, kind: str, key: str, ext: str) -> Path:
        if kind not in KINDS or "/" in key or "\\" in key or ".." in key:
            raise ValueError(f"invalid cache address {kind}/{key}")
        return self.base / kind / f"{key}.{ext}"

    def get_text(self, kind: str, key: str, ext: str) -> str | None:
        p = self.path(kind, key, ext)
        return p.read_text(encoding="utf-8") if p.is_file() else None

    def put_text(self, kind: str, key: str, ext: str, text: str) -> Path:
        return atomic_write(self.path(kind, key, ext), text)

    def get_bytes(self, kind: str, key: str, ext: str) -> bytes | None:
        p = self.path(kind, key, ext)
        return p.read_bytes() if p.is_file() else None

    def put_bytes(self, kind: str, key: str, ext: str, data: bytes) -> Path:
        return atomic_write(self.path(kind, key, ext), data)

    def exists(self, kind: str, key: str, ext: str) -> bool:
        return self.path(kind, key, ext).is_file()

    def prune(self, older_than: timedelta, *, now: float | None = None) -> int:
        """Delete entries not modified within older_than. Returns the number removed."""
        cutoff = (now if now is not None else time.time()) - older_than.total_seconds()
        removed = 0
        for f in self.base.rglob("*"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        return removed

    def info(self) -> CacheInfo:
        entries = dict.fromkeys(KINDS, 0)
        total = 0
        for kind in KINDS:
            d = self.base / kind
            if d.is_dir():
                for f in d.iterdir():
                    if f.is_file():
                        entries[kind] += 1
                        total += f.stat().st_size
        return CacheInfo(root=str(self.root), entries=entries, bytes=total)


def parse_age(text: str) -> timedelta:
    """Parse '30d', '12h', '45m' for `cache prune --older-than`."""
    units = {"d": "days", "h": "hours", "m": "minutes"}
    if len(text) < 2 or text[-1] not in units or not text[:-1].isdigit():
        raise ValueError(f"invalid age {text!r}; use forms like 30d, 12h, 45m")
    return timedelta(**{units[text[-1]]: int(text[:-1])})
