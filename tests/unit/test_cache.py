import os
import time
from datetime import timedelta
from pathlib import Path

import pytest

from audio_smith.cache import CacheStore
from audio_smith.cache.keys import CACHE_FORMAT, blocks_key, chunk_key, script_key, track_key
from audio_smith.cache.store import parse_age


def test_cache_key_format_versioned() -> None:
    for key in (
        blocks_key("<p>x</p>", ()),
        script_key("h", "p@1", "l", "en", 1, "main"),
        chunk_key("t", "maya2", "m", "dad", "c", 0.9, 1),
        track_key(["a"], "m"),
    ):
        assert key.startswith(f"{CACHE_FORMAT}-")


def test_cache_version_bump_invalidates_old_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = CacheStore(tmp_path)
    key = blocks_key("<p>x</p>", ())
    store.put_text("blocks", key, "json", "{}")
    import audio_smith.cache.store as st
    from audio_smith.cache import keys

    monkeypatch.setattr(keys, "CACHE_FORMAT", "v2")
    monkeypatch.setattr(st, "CACHE_FORMAT", "v2")
    new_key = keys.blocks_key("<p>x</p>", ())
    assert new_key != key
    assert CacheStore(tmp_path).get_text("blocks", new_key, "json") is None


def test_cache_content_addressed_blocks_scripts_chunks_outputs(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    for kind in ("blocks", "scripts", "chunks", "tracks"):
        store.put_bytes(kind, "k1", "bin", b"data")
        assert store.get_bytes(kind, "k1", "bin") == b"data"
        assert store.exists(kind, "k1", "bin")
        assert store.path(kind, "k1", "bin") == tmp_path / CACHE_FORMAT / kind / "k1.bin"
    assert store.get_bytes("chunks", "missing", "wav") is None
    info = store.info()
    assert info.entries["chunks"] == 1 and info.bytes == 16


def test_cache_rejects_traversal_addresses(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    for kind, key in (("blocks", "../x"), ("evil", "k"), ("chunks", "a/b")):
        with pytest.raises(ValueError):
            store.path(kind, key, "wav")


def test_cache_keys_change_with_every_input() -> None:
    base = dict(text="t", backend="maya2", model="m", voice_id="dad", voice_clip_hash="c", rate=0.9, seed=1)
    k = chunk_key(**base)  # type: ignore[arg-type]
    for field, value in (("text", "u"), ("voice_clip_hash", "d"), ("rate", 1.0), ("seed", 2), ("model", "n")):
        assert chunk_key(**{**base, field: value}) != k  # type: ignore[arg-type]
    assert chunk_key(**base) == k  # type: ignore[arg-type]


def test_cache_prune_older_than_30d_removes_old_only(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    old = store.put_text("scripts", "old", "md", "x")
    store.put_text("scripts", "new", "md", "y")
    past = time.time() - 31 * 86400
    os.utime(old, (past, past))
    assert store.prune(parse_age("30d")) == 1
    assert store.get_text("scripts", "new", "md") == "y"
    assert store.get_text("scripts", "old", "md") is None


def test_cache_parse_age_forms() -> None:
    assert parse_age("12h") == timedelta(hours=12)
    assert parse_age("45m") == timedelta(minutes=45)
    for bad in ("30", "d", "3w", "x1d"):
        with pytest.raises(ValueError):
            parse_age(bad)
