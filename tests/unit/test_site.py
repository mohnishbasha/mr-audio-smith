"""Site batch mode (TEST_PLAN 5.20): discovery, incremental runs, failure isolation, injection."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from audio_smith import pipeline, site
from audio_smith.cli import app
from audio_smith.config import Settings
from audio_smith.errors import SynthesisError, UsageError
from audio_smith.fetch import FetchResult
from audio_smith.llm.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "tests" / "fixtures" / "pages"
LLM = ROOT / "tests" / "fixtures" / "llm"
BASE = "https://www.aadhish.us/"
INDEX = BASE + "messages-from-dad.html"
LETTER_GLOB = "letter-*.html"
FIXTURE_LETTERS = 12


def _index_html() -> str:
    return (PAGES / "index-messages.html").read_text(encoding="utf-8")


def _page(url: str, content: str) -> FetchResult:
    return FetchResult(
        url=url, content=content, content_type="text/html", encoding="utf-8", is_local=False, fetched_bytes=1
    )


def _three_page_index() -> str:
    links = "".join(f'<a href="/letter-{n}.html">{n}</a>' for n in ("a", "b", "c"))
    return f"<html><body>{links}</body></html>"


def _fake_fetcher(index_html: str, page_html: str = "") -> Any:
    def fetcher(url: str, settings: Settings) -> FetchResult:
        return _page(url, index_html if url == INDEX else page_html)

    return fetcher


def _result(cached: bool, manifest: object | None = None) -> SimpleNamespace:
    track = SimpleNamespace(cached=cached)
    return SimpleNamespace(tracks=[track], manifest=manifest, manifest_path=Path("m.json"))


def _kwargs() -> dict[str, Any]:
    return {"backend": "mock", "settings": Settings()}


def test_site_same_origin_links_only() -> None:
    html = (
        '<a href="/letter-1.html">1</a><a href="https://evil.example/letter-2.html">2</a>'
        '<a href="//cdn.example/letter-3.html">3</a><a href="http://www.aadhish.us/letter-4.html">4</a>'
        '<a href="letter-5.html#top">5</a>'
    )
    pages = site.discover_pages(html, BASE, match_glob=LETTER_GLOB, max_pages=50)
    assert pages == [BASE + "letter-1.html", BASE + "letter-5.html"]


def test_site_match_glob_filters_links() -> None:
    pages = site.discover_pages(_index_html(), INDEX, match_glob=LETTER_GLOB, max_pages=50)
    assert len(pages) == FIXTURE_LETTERS
    assert all(p.startswith(BASE + "letter-") and p.endswith(".html") for p in pages)
    assert BASE + "letter-pi-infinity.html" in pages
    assert len(set(pages)) == len(pages)
    assert site.discover_pages(_index_html(), INDEX, match_glob="about.html", max_pages=50) == [
        BASE + "about.html"
    ]


def test_site_max_pages_limit_respected() -> None:
    pages = site.discover_pages(_index_html(), INDEX, match_glob=LETTER_GLOB, max_pages=3)
    assert len(pages) == 3


def test_site_unchanged_page_skipped_by_hash() -> None:
    calls: list[str] = []

    def narrate(page: str, **kwargs: Any) -> SimpleNamespace:
        calls.append(page)
        return _result(cached=len(calls) > 3)

    fetcher = _fake_fetcher(_three_page_index())
    first = site.narrate_site(
        INDEX, match_glob=LETTER_GLOB, narrate_kwargs=_kwargs(), fetcher=fetcher, narrate=narrate
    )
    again = site.narrate_site(
        INDEX, match_glob=LETTER_GLOB, narrate_kwargs=_kwargs(), fetcher=fetcher, narrate=narrate
    )
    assert [r.status for r in first] == ["rendered"] * 3
    assert [r.status for r in again] == ["cached"] * 3


def test_site_shares_one_backend_instance_across_pages() -> None:
    seen: list[object] = []

    def narrate(page: str, **kwargs: Any) -> SimpleNamespace:
        seen.append(kwargs["tts"])
        return _result(cached=False)

    site.narrate_site(
        INDEX,
        match_glob=LETTER_GLOB,
        narrate_kwargs=_kwargs(),
        fetcher=_fake_fetcher(_three_page_index()),
        narrate=narrate,
    )
    assert len(seen) == 3 and all(t is seen[0] for t in seen)


def test_site_fixture_index_second_run_renders_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)
    letter = (PAGES / "letter-calm.html").read_text(encoding="utf-8")
    kwargs = {
        "llm": "fake",
        "backend": "mock",
        "out": tmp_path / "out",
        "provider": FakeProvider(LLM),
        "settings": Settings(),
    }
    run = lambda: site.narrate_site(  # noqa: E731
        INDEX,
        match_glob=LETTER_GLOB,
        max_pages=3,
        narrate_kwargs=dict(kwargs),
        fetcher=_fake_fetcher(_three_page_index(), letter),
    )
    first, second = run(), run()
    assert first[0].status == "rendered"  # identical page bytes share cache entries, later pages may hit
    assert [r.status for r in second] == ["cached"] * 3
    assert all(r.manifest_path is not None and r.manifest_path.is_file() for r in second)


def test_site_one_page_failure_does_not_abort_batch() -> None:
    def narrate(page: str, **kwargs: Any) -> SimpleNamespace:
        if page.endswith("letter-b.html"):
            raise SynthesisError("backend exploded")
        return _result(cached=False)

    rows = site.narrate_site(
        INDEX,
        match_glob=LETTER_GLOB,
        narrate_kwargs=_kwargs(),
        fetcher=_fake_fetcher(_three_page_index()),
        narrate=narrate,
    )
    assert [r.status for r in rows] == ["rendered", "failed", "rendered"]
    assert rows[1].error == "backend exploded"


def test_site_inject_root_maps_urls_to_local_files(tmp_path: Path) -> None:
    for n in ("a", "b", "c"):
        (tmp_path / f"letter-{n}.html").write_text("<h1>x</h1>", encoding="utf-8")
    injected: list[tuple[Path, str, str]] = []

    def inject(path: Path, snippet: str, *, selector: str, dry_run: bool) -> None:
        injected.append((path, snippet, selector))
        assert dry_run is False

    rows = site.narrate_site(
        INDEX,
        match_glob=LETTER_GLOB,
        inject_root=tmp_path,
        selector="h2",
        narrate_kwargs=_kwargs(),
        fetcher=_fake_fetcher(_three_page_index()),
        narrate=lambda page, **kw: _result(cached=False, manifest=object()),
        inject=inject,
        embed=lambda manifest: "<snippet>",
    )
    assert [p for p, _, _ in injected] == [tmp_path.resolve() / f"letter-{n}.html" for n in ("a", "b", "c")]
    assert {s for _, s, _ in injected} == {"<snippet>"} and {sel for _, _, sel in injected} == {"h2"}
    assert [r.injected for r in rows] == [p for p, _, _ in injected]


def test_site_inject_root_rejects_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "public"
    root.mkdir()
    (tmp_path / "secret.html").write_text("<h1>x</h1>", encoding="utf-8")
    with pytest.raises(UsageError):
        site.local_file_for(root, BASE + "..%2fsecret.html")
    assert site.local_file_for(root, BASE + "sub/") == (root / "sub" / "index.html").resolve()


def test_site_missing_local_file_is_a_failed_row(tmp_path: Path) -> None:
    rows = site.narrate_site(
        INDEX,
        match_glob=LETTER_GLOB,
        inject_root=tmp_path,
        narrate_kwargs=_kwargs(),
        fetcher=_fake_fetcher(_three_page_index()),
        narrate=lambda page, **kw: _result(cached=False, manifest=object()),
        inject=lambda *a, **k: None,
        embed=lambda m: "",
    )
    assert [r.status for r in rows] == ["failed"] * 3
    assert rows[0].error is not None and "No local file" in rows[0].error


def _rows(*statuses: site.Status) -> list[site.SiteRow]:
    return [
        site.SiteRow(page=f"{BASE}letter-{i}.html", status=s, duration_s=1.5) for i, s in enumerate(statuses)
    ]


def test_site_summary_table_columns_page_status_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(site, "narrate_site", lambda *a, **k: _rows("cached", "rendered"))
    res = CliRunner().invoke(app, ["site", INDEX, "--match", LETTER_GLOB, "--backend", "mock"])
    assert res.exit_code == 0, res.output
    for text in ("page", "status", "duration", "cached", "rendered", "1.5s", "letter-0.html"):
        assert text in res.output


def test_site_cli_exit_code_6_when_any_page_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake(index: str, **kwargs: Any) -> list[site.SiteRow]:
        captured.update(kwargs)
        return _rows("rendered", "failed")

    monkeypatch.setattr(site, "narrate_site", fake)
    res = CliRunner().invoke(
        app,
        ["site", INDEX, "--match", LETTER_GLOB, "--max-pages", "4", "--selector", "h2", "--profile", "kid-5"],
    )
    assert res.exit_code == 6
    assert captured["max_pages"] == 4 and captured["selector"] == "h2"
    assert captured["narrate_kwargs"]["profile"] == "kid-5"
