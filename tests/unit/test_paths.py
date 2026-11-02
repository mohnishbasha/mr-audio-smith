from pathlib import Path

import pytest

from audio_smith.errors import UsageError
from audio_smith.paths import atomic_write, ensure_inside, safe_slug


@pytest.mark.parametrize(
    ("source", "slug"),
    [
        ("https://www.aadhish.us/letter-calm-in-the-chaos.html", "letter-calm-in-the-chaos"),
        ("tests/fixtures/pages/letter-calm.html", "letter-calm"),
        ("https://example.com/../../etc/passwd", "passwd"),
        ("https://example.com/a/b/", "b"),
        ("https://example.com/", "example-com"),
        ("https://example.com/Caf%C3%A9 Story.html", "cafe-story"),
        ("..", "page"),
    ],
)
def test_paths_safe_slug_sanitizes(source: str, slug: str) -> None:
    assert safe_slug(source) == slug


def test_paths_ensure_inside_blocks_traversal(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        ensure_inside(tmp_path / "out", tmp_path / "out" / ".." / "evil")
    assert ensure_inside(tmp_path, tmp_path / "a" / "b") == (tmp_path / "a" / "b").resolve()


def test_paths_atomic_write_replaces_and_sets_mode(tmp_path: Path) -> None:
    target = tmp_path / "x" / "f.txt"
    atomic_write(target, "one")
    atomic_write(target, b"two", mode=0o600)
    assert target.read_text() == "two"
    assert (target.stat().st_mode & 0o777) == 0o600
    assert [p.name for p in target.parent.iterdir()] == ["f.txt"]
