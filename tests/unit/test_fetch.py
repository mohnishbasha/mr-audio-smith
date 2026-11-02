from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from audio_smith import __version__
from audio_smith.config import Settings
from audio_smith.errors import FetchError
from audio_smith.fetch import MAX_REDIRECTS, FetchResult, default_resolver, fetch

PUBLIC_IP = "93.184.216.34"
HTML = "<html><body><p>Hello</p></body></html>"
HTML_HEADERS = {"content-type": "text/html; charset=utf-8"}


def resolver_for(mapping: dict[str, list[str]] | None = None, default: str = PUBLIC_IP) -> Any:
    table = mapping or {}

    def resolve(host: str) -> list[str]:
        return table.get(host, [default])

    return resolve


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def run(url: str, settings: Settings, resolver: Any = None) -> FetchResult:
    with httpx.Client() as client:
        return fetch(url, settings, client=client, resolver=resolver or resolver_for())


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "169.254.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "100.64.0.1",
        "fd00:ec2::254",
        "0.0.0.0",  # noqa: S104
        "224.0.0.1",
        "::ffff:127.0.0.1",
    ],
)
def test_fetch_private_ip_blocked(ip: str, settings: Settings, mock: respx.MockRouter) -> None:
    with pytest.raises(FetchError, match="non-public") as exc:
        run("http://evil.test/", settings, resolver_for(default=ip))
    assert exc.value.hint
    assert not mock.calls


def test_fetch_private_ip_literal_and_any_answer_blocked(settings: Settings) -> None:
    with pytest.raises(FetchError, match="non-public"):
        run("http://127.0.0.1:8080/", settings)
    with pytest.raises(FetchError, match="non-public"):
        run("http://multi.test/", settings, resolver_for({"multi.test": [PUBLIC_IP, "10.0.0.1"]}))


def test_fetch_metadata_hostname_blocked(settings: Settings) -> None:
    with pytest.raises(FetchError, match="metadata"):
        run("http://metadata.google.internal/computeMetadata/v1/", settings)


def test_fetch_empty_resolution_rejected(settings: Settings) -> None:
    with pytest.raises(FetchError, match="No addresses"):
        run("http://empty.test/", settings, resolver_for({"empty.test": []}))


def test_fetch_redirect_to_private_blocked(settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/start").respond(302, headers={"location": "http://internal.test/admin"})
    resolver = resolver_for({"internal.test": ["10.1.2.3"]})
    with pytest.raises(FetchError, match="non-public"):
        run("http://pub.test/start", settings, resolver)
    assert mock.calls.call_count == 1


def test_fetch_redirect_to_non_http_scheme_blocked(settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").respond(302, headers={"location": "file:///etc/passwd"})
    with pytest.raises(FetchError, match="Unsupported"):
        run("http://pub.test/", settings)


def test_fetch_allow_private_flag_permits_loopback(mock: respx.MockRouter) -> None:
    mock.get("http://127.0.0.1:8080/page").respond(200, text=HTML, headers=HTML_HEADERS)
    result = run("http://127.0.0.1:8080/page", Settings(allow_private=True))
    assert result.content == HTML
    assert result.is_local is False


def test_fetch_dns_rebinding_connects_to_resolved_ip(settings: Settings, mock: respx.MockRouter) -> None:
    route = mock.get(f"https://{PUBLIC_IP}/p").respond(200, text=HTML, headers=HTML_HEADERS)
    answers = iter([[PUBLIC_IP], ["127.0.0.1"]])
    calls: list[str] = []

    def rebinding(host: str) -> list[str]:
        calls.append(host)
        return next(answers)

    result = run("https://rebind.test/p", settings, rebinding)
    request = route.calls.last.request
    assert calls == ["rebind.test"]
    assert request.url.host == PUBLIC_IP
    assert request.headers["host"] == "rebind.test"
    assert request.extensions["sni_hostname"] == "rebind.test"
    assert result.url == "https://rebind.test/p"


def test_fetch_pinned_request_keeps_port_and_ipv6_host_header(
    settings: Settings, mock: respx.MockRouter
) -> None:
    route = mock.get("http://[2606:2800:220:1::1]:8080/x").respond(200, text=HTML, headers=HTML_HEADERS)
    run("http://v6.test:8080/x", settings, resolver_for(default="2606:2800:220:1::1"))
    assert route.calls.last.request.headers["host"] == "v6.test:8080"
    run("http://[2606:2800:220:1::1]:8080/x", settings)
    assert route.calls.last.request.headers["host"] == "[2606:2800:220:1::1]:8080"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a",
        "gopher://example.com/",
        "javascript:alert(1)",
        "data:text/html,<p>x</p>",
        "mailto:a@b.c",
        "http:///nohost",
    ],
)
def test_fetch_non_http_scheme_rejected(url: str, settings: Settings) -> None:
    with pytest.raises(FetchError) as exc:
        run(url, settings)
    assert exc.value.hint
    assert exc.value.code == "fetch_failed"


def test_fetch_timeout_default_20s_honored(settings: Settings, mock: respx.MockRouter) -> None:
    route = mock.get(f"http://{PUBLIC_IP}/").respond(200, text=HTML, headers=HTML_HEADERS)
    run("http://pub.test/", settings)
    assert route.calls.last.request.extensions["timeout"]["read"] == 20.0
    run("http://pub.test/", Settings(fetch_timeout_s=3.5))
    assert route.calls.last.request.extensions["timeout"]["read"] == 3.5


def test_fetch_timeout_raises_fetch_error(settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(FetchError, match="Timed out"):
        run("http://pub.test/", settings)


def test_fetch_network_error_raises_fetch_error(settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(FetchError, match="Network error"):
        run("http://pub.test/", settings)


def test_fetch_total_time_budget_enforced(mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    mock.get(f"http://{PUBLIC_IP}/").respond(200, content=b"x" * 10, headers=HTML_HEADERS)
    ticks = iter([0.0, 1000.0, 1000.0, 1000.0])
    monkeypatch.setattr("audio_smith.fetch.time.monotonic", lambda: next(ticks))
    with pytest.raises(FetchError, match="time budget"):
        run("http://pub.test/", Settings())


class CountingStream(httpx.SyncByteStream):
    def __init__(self, chunks: int, size: int) -> None:
        self.chunks, self.size, self.sent = chunks, size, 0

    def __iter__(self) -> Iterator[bytes]:
        for _ in range(self.chunks):
            self.sent += 1
            yield b"a" * self.size


def test_fetch_max_size_5mb_aborts_stream(settings: Settings, mock: respx.MockRouter) -> None:
    stream = CountingStream(chunks=100, size=1024 * 1024)
    mock.get(f"http://{PUBLIC_IP}/big").mock(
        return_value=httpx.Response(200, headers=HTML_HEADERS, stream=stream)
    )
    with pytest.raises(FetchError, match="too large"):
        run("http://pub.test/big", settings)
    assert stream.sent == 6


def test_fetch_content_length_over_limit_rejected_early(settings: Settings, mock: respx.MockRouter) -> None:
    stream = CountingStream(chunks=1, size=10)
    headers = {**HTML_HEADERS, "content-length": str(6 * 1024 * 1024)}
    mock.get(f"http://{PUBLIC_IP}/big").mock(return_value=httpx.Response(200, headers=headers, stream=stream))
    with pytest.raises(FetchError, match="too large"):
        run("http://pub.test/big", settings)
    assert stream.sent == 0


def test_fetch_redirect_limit_5_enforced(settings: Settings, mock: respx.MockRouter) -> None:
    for i in range(MAX_REDIRECTS + 2):
        mock.get(f"http://{PUBLIC_IP}/r{i}").respond(302, headers={"location": f"/r{i + 1}"})
    with pytest.raises(FetchError, match="Too many redirects"):
        run("http://pub.test/r0", settings)
    assert mock.calls.call_count == MAX_REDIRECTS + 1


def test_fetch_five_redirects_then_success(settings: Settings, mock: respx.MockRouter) -> None:
    for i in range(MAX_REDIRECTS):
        mock.get(f"http://{PUBLIC_IP}/r{i}").respond(301, headers={"location": f"/r{i + 1}"})
    mock.get(f"http://{PUBLIC_IP}/r{MAX_REDIRECTS}").respond(200, text=HTML, headers=HTML_HEADERS)
    result = run("http://pub.test/r0", settings)
    assert result.url == f"http://pub.test/r{MAX_REDIRECTS}"


def test_fetch_user_agent_descriptive_sent(settings: Settings, mock: respx.MockRouter) -> None:
    route = mock.get(f"http://{PUBLIC_IP}/").respond(200, text=HTML, headers=HTML_HEADERS)
    run("http://pub.test/", settings)
    ua = route.calls.last.request.headers["user-agent"]
    assert ua == f"mr-audio-smith/{__version__} (+https://getaudiosmith.com)"


def test_fetch_local_file_no_network(settings: Settings, tmp_path: Path, mock: respx.MockRouter) -> None:
    html = tmp_path / "a.html"
    html.write_text("<p>café</p>", encoding="utf-8")
    md = tmp_path / "b.MD"
    md.write_text("# Title", encoding="utf-8")
    r1 = fetch(str(html), settings)
    r2 = fetch(md.as_uri(), settings)
    assert (r1.content, r1.content_type, r1.is_local) == ("<p>café</p>", "text/html", True)
    assert (r2.content, r2.content_type, r2.is_local) == ("# Title", "text/markdown", True)
    assert r1.fetched_bytes == len("<p>café</p>".encode())
    assert not mock.calls


def test_fetch_local_bad_extension_missing_and_oversize(tmp_path: Path) -> None:
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(FetchError, match="Unsupported local file type"):
        fetch(str(exe), Settings())
    with pytest.raises(FetchError, match="Cannot read"):
        fetch(str(tmp_path / "missing.html"), Settings())
    big = tmp_path / "big.html"
    big.write_bytes(b"a" * 11)
    with pytest.raises(FetchError, match="too large"):
        fetch(str(big), Settings(max_fetch_bytes=10))


def test_fetch_charset_from_content_type_decoded(settings: Settings, mock: respx.MockRouter) -> None:
    body = "<p>café ü</p>".encode("iso-8859-1")
    mock.get(f"http://{PUBLIC_IP}/").respond(
        200, content=body, headers={"content-type": 'text/html; charset="ISO-8859-1"'}
    )
    result = run("http://pub.test/", settings)
    assert result.content == "<p>café ü</p>"
    assert result.encoding == "iso-8859-1"


def test_fetch_unknown_or_missing_charset_falls_back_to_utf8(
    settings: Settings, mock: respx.MockRouter
) -> None:
    mock.get(f"http://{PUBLIC_IP}/a").respond(
        200, content=b"ok \xff", headers={"content-type": "text/html; charset=nope"}
    )
    mock.get(f"http://{PUBLIC_IP}/b").respond(200, content=b"plain")
    a = run("http://pub.test/a", settings)
    b = run("http://pub.test/b", settings)
    assert a.content == "ok �"
    assert a.encoding == "utf-8"
    assert (b.content, b.content_type, b.encoding) == ("plain", "text/html", "utf-8")


@pytest.mark.parametrize("ctype", ["image/png", "application/octet-stream", "application/pdf"])
def test_fetch_non_text_content_type_rejected(ctype: str, settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").respond(200, content=b"\x89PNG", headers={"content-type": ctype})
    with pytest.raises(FetchError, match="content type"):
        run("http://pub.test/", settings)


@pytest.mark.parametrize("status", [404, 500])
def test_fetch_http_error_names_status(status: int, settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").respond(status)
    with pytest.raises(FetchError, match=f"HTTP {status}"):
        run("http://pub.test/", settings)


def test_fetch_redirect_without_location_is_not_followed(settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").respond(302, text="moved", headers=HTML_HEADERS)
    result = run("http://pub.test/", settings)
    assert result.content == "moved"


def test_fetch_hostile_page_within_limits(settings: Settings, mock: respx.MockRouter) -> None:
    payload = ("A" * 3 * 1024 * 1024).encode()
    mock.get(f"http://{PUBLIC_IP}/hostile").respond(200, content=payload, headers=HTML_HEADERS)
    result = run("http://pub.test/hostile", settings)
    assert result.fetched_bytes == len(payload)


def test_fetch_creates_and_closes_own_client(settings: Settings, mock: respx.MockRouter) -> None:
    mock.get(f"http://{PUBLIC_IP}/").respond(200, text=HTML, headers=HTML_HEADERS)
    result = fetch("http://pub.test/", settings, resolver=resolver_for())
    assert result.content == HTML


def test_default_resolver_localhost_and_failure() -> None:
    assert "127.0.0.1" in default_resolver("localhost")
    with pytest.raises(FetchError, match="Cannot resolve"):
        default_resolver("nonexistent.invalid")
