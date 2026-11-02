import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from audio_smith import api
from audio_smith.cli import app
from audio_smith.config import Settings, load_settings
from audio_smith.fetch import FetchResult
from audio_smith.llm.fake import FakeProvider
from audio_smith.script.markdown import parse_script

PAGES = Path(__file__).resolve().parents[1] / "fixtures" / "pages"
SIG = "Love you to the moon, Mom"


def _fetcher(html: str, url: str = "https://example.com/rainy-day.html"):  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def fetch(source: str, settings: Settings) -> FetchResult:
        calls.append(source)
        return FetchResult(
            url=url,
            content=html,
            content_type="text/html",
            encoding="utf-8",
            is_local=False,
            fetched_bytes=len(html),
        )

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def _main_body() -> str:
    body = "\n\n".join(
        f"## {i:03d}\nRain is falling on our window today. We can jump in puddles later."
        for i in range(1, 44)
    )
    return (
        body
        + f"\n\n## 044 {{verbatim}}\nKeep this sentence exactly as written.\n\n## 045 {{verbatim}}\n{SIG}"
    )


def _parent_body() -> str:
    return "\n\n".join(
        f"## {i:03d}\nWet shoes go by the door, please. Thank you for helping." for i in range(1, 26)
    )


def test_api_write_script_writes_blocks_and_scripts(tmp_path: Path) -> None:
    html = (PAGES / "data-narrate.html").read_text()
    provider = FakeProvider(responses=[_main_body(), _parent_body()])
    res = api.write_script(
        "https://example.com/rainy-day.html",
        llm="fake",
        out=tmp_path / "out",
        provider=provider,
        fetcher=_fetcher(html),
        backend="mock",
        voice="dad",
    )
    assert res.slug == "rainy-day"
    assert res.blocks_path == (tmp_path / "out" / "rainy-day" / "rainy-day.blocks.json").resolve()
    script = parse_script(res.scripts["en"].read_text())
    assert script.chunks[-1].verbatim and script.meta.profile == "kid-5@1.0.0"
    assert res.parent_script is not None
    assert parse_script(res.parent_script.read_text()).meta.profile == "adult-brief@1.0.0"
    assert res.cache_hits == {"blocks": False, "script": False}


def test_cache_unchanged_page_skips_render(tmp_path: Path) -> None:
    html = (PAGES / "data-narrate.html").read_text()
    provider = FakeProvider(responses=[_main_body(), _parent_body()])
    kwargs = dict(llm="fake", out=tmp_path / "out", provider=provider, backend="mock", voice="dad")
    api.write_script("https://example.com/rainy-day.html", fetcher=_fetcher(html), **kwargs)  # type: ignore[arg-type]
    start = time.monotonic()
    second = api.write_script("https://example.com/rainy-day.html", fetcher=_fetcher(html), **kwargs)  # type: ignore[arg-type]
    assert time.monotonic() - start < 2.0
    assert second.cache_hits == {"blocks": True, "script": True}
    assert len(provider.calls) == 2


def test_cache_force_flag_bypasses(tmp_path: Path) -> None:
    html = (PAGES / "data-narrate.html").read_text()
    provider = FakeProvider(responses=[_main_body(), _parent_body(), _main_body(), _parent_body()])
    kwargs = dict(llm="fake", out=tmp_path / "out", provider=provider, backend="mock", voice="dad")
    api.write_script("https://example.com/rainy-day.html", fetcher=_fetcher(html), **kwargs)  # type: ignore[arg-type]
    res = api.write_script("https://example.com/rainy-day.html", fetcher=_fetcher(html), force=True, **kwargs)  # type: ignore[arg-type]
    assert res.cache_hits == {"blocks": False, "script": False}
    assert len(provider.calls) == 4


def test_api_markdown_source_extracts_blocks(tmp_path: Path) -> None:
    md = "# Hello\n\nA first paragraph.\n\n## Part\n- one\n- two\n\n> quoted\n"
    doc, hit = api.extract("note.md", fetcher=_fetcher(md, url="note.md"))
    assert [b.type for b in doc.blocks] == [
        "title",
        "paragraph",
        "heading",
        "list_item",
        "list_item",
        "quote",
    ]
    assert not hit


def test_api_markdown_to_html_closes_trailing_list() -> None:
    assert api.markdown_to_html("- a\n- b").endswith("</ul></article>")


def test_cli_script_command_with_local_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "rainy-day.html"
    page.write_text((PAGES / "data-narrate.html").read_text())
    queue = [_main_body(), _parent_body()]
    import audio_smith.api as api_mod

    monkeypatch.setattr(api_mod, "get_provider", lambda spec, s: FakeProvider(responses=queue))
    result = CliRunner().invoke(app, ["script", str(page), "--llm", "fake", "--out", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "rainy-day.en.script.md" in result.output
    assert (tmp_path / "out" / "rainy-day" / "rainy-day.blocks.json").is_file()


def test_cli_profile_list_show_validate_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    out = runner.invoke(app, ["profile", "list"])
    assert out.exit_code == 0 and "kid-5" in out.output
    show = runner.invoke(app, ["profile", "show", "kid-5"])
    assert show.exit_code == 0 and '"rate": 0.9' in show.output
    assert runner.invoke(app, ["profile", "show", "nope"]).exit_code != 0
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nversion: 1.0.0\nspeech:\n  rate: 9\n")
    assert runner.invoke(app, ["profile", "validate", str(bad)]).exit_code != 0
    good = tmp_path / "good.yaml"
    good.write_text("id: x\nversion: 1.0.0\n")
    ok = runner.invoke(app, ["profile", "validate", str(good)])
    assert ok.exit_code == 0 and "x@1.0.0" in ok.output
    assert '"title": "audio-smith/profile@1"' in runner.invoke(app, ["profile", "schema"]).output


def test_cli_cache_info_and_prune(tmp_path: Path) -> None:
    runner = CliRunner()
    assert "blocks: 0" in runner.invoke(app, ["cache", "info"]).output
    assert "removed 0" in runner.invoke(app, ["cache", "prune", "--older-than", "30d"]).output
    assert runner.invoke(app, ["cache", "prune", "--older-than", "soon"]).exit_code != 0


def test_api_resolve_profile_uses_settings_default() -> None:
    assert api.resolve_profile(None, load_settings()).id == "kid-5"
