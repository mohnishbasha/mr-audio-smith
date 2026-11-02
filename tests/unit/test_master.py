# mypy: disable-error-code="no-untyped-call"
"""Assembly, peaks, stings, mastering arguments, and tags (TEST_PLAN 5.12 and 5.13)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest
import soundfile as sf
from mutagen.id3 import ID3

from audio_smith import proc
from audio_smith.config import Settings
from audio_smith.errors import FetchError, MasteringError
from audio_smith.master import ffmpeg as ff
from audio_smith.master.assemble import assemble, resample
from audio_smith.master.ffmpeg_graph import Measured, build_filter_graph
from audio_smith.master.peaks import compute_peaks, peaks_attr
from audio_smith.master.stings import resolve_sting
from audio_smith.master.tags import detect_image_mime, fetch_cover, http_get_bytes, write_tags
from audio_smith.pipeline_types import MASTER_SAMPLE_RATE, AssembledTrack, RenderedUnit, SynthUnit

ROOT = Path(__file__).parents[2]
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _unit(chunk: str, idx: int, seconds: float, rate: int = 24_000, pause: int = 0) -> RenderedUnit:
    t = np.arange(round(seconds * rate)) / rate
    samples = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    unit = SynthUnit(
        chunk_id=chunk, index=idx, text=f"t{idx}", display_text=f"Text {idx}.", pause_after_ms=pause
    )
    return RenderedUnit(unit=unit, samples=samples, sample_rate=rate)


# --- 5.12 assemble ---


def test_assemble_total_duration_equals_parts_plus_pauses() -> None:
    units = [_unit("c1", 0, 1.0, pause=300), _unit("c1", 1, 0.5), _unit("c2", 2, 0.8)]
    track = assemble(units, pause_between_chunks_ms=400, crossfade_ms=0)
    expected_ms = 1000 + 300 + 500 + 400 + 800
    assert abs(track.duration_ms - expected_ms) <= 5


def test_assemble_crossfade_10ms_at_joins() -> None:
    units = [_unit("c1", 0, 1.0), _unit("c1", 1, 1.0)]
    track = assemble(units, pause_between_chunks_ms=0, crossfade_ms=10)
    assert 1990 - 5 <= track.duration_ms <= 2000
    assert float(np.max(np.abs(np.diff(track.samples)))) < 0.1  # no clicks anywhere


def test_assemble_no_clicks_around_silence() -> None:
    track = assemble([_unit("a", 0, 0.5), _unit("b", 1, 0.5)], pause_between_chunks_ms=200)
    assert abs(float(track.samples[0])) < 0.01
    assert float(np.max(np.abs(np.diff(track.samples)))) < 0.1


def test_assemble_resamples_to_44100() -> None:
    track = assemble([_unit("a", 0, 1.0, rate=16_000)], pause_between_chunks_ms=0)
    assert track.sample_rate == MASTER_SAMPLE_RATE
    assert abs(len(track.samples) - MASTER_SAMPLE_RATE) <= 2
    assert resample(np.zeros(5, dtype=np.float32), 44_100, 44_100).shape == (5,)


def test_assemble_chunk_timestamps_within_10ms() -> None:
    units = [_unit("c1", 0, 1.0, pause=100), _unit("c1", 1, 0.5), _unit("c2", 2, 1.0)]
    track = assemble(units, pause_between_chunks_ms=500, crossfade_ms=10)
    first, second = track.spans
    assert first.start_ms == 0
    assert abs(first.end_ms - 1600) <= 10
    assert abs(second.start_ms - 2100) <= 10
    assert first.start_ms < first.end_ms <= second.start_ms < second.end_ms
    assert first.text == "Text 0. Text 1."
    assert abs(second.end_ms - track.duration_ms) <= 10


def test_assemble_heading_and_chunk_pauses_from_profile() -> None:
    units = [_unit("h", 0, 0.5, pause=700), _unit("c", 1, 0.5)]
    with_pauses = assemble(units, pause_between_chunks_ms=300, crossfade_ms=0)
    assert abs(with_pauses.duration_ms - (500 + 700 + 300 + 500)) <= 5


def test_assemble_empty_and_short_units() -> None:
    assert assemble([], pause_between_chunks_ms=0).duration_ms == 0
    tiny = [_unit("a", 0, 0.001), _unit("a", 1, 0.001)]
    assert len(assemble(tiny, pause_between_chunks_ms=0).samples) > 0


# --- peaks ---


def test_peaks_normalized_28_bars() -> None:
    samples = np.concatenate([np.full(100, 0.25), np.full(100, 0.5)]).astype(np.float32)
    peaks = compute_peaks(samples)
    assert len(peaks) == 28
    assert max(peaks) == 1.0
    assert min(peaks) == 0.5
    assert all(0.0 <= p <= 1.0 for p in peaks)


def test_peaks_edge_cases_and_attr() -> None:
    assert compute_peaks(np.zeros(0, dtype=np.float32)) == [0.0] * 28
    assert compute_peaks(np.zeros(100, dtype=np.float32), bars=4) == [0.0] * 4
    with pytest.raises(ValueError):
        compute_peaks(np.zeros(4, dtype=np.float32), bars=0)
    assert peaks_attr([0.0, 0.5, 1.0, 0.126]) == "0,50,100,13"
    assert len(compute_peaks(np.ones(3, dtype=np.float32), bars=28)) == 28


# --- stings ---


def test_master_stings_are_procedural_and_documented() -> None:
    licenses = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    for wav in (ROOT / "assets" / "stings").glob("*.wav"):
        assert wav.name in licenses
        info = sf.info(wav)
        assert (info.samplerate, info.channels, info.subtype) == (44_100, 1, "PCM_16")
    spec = importlib.util.spec_from_file_location("sting_gen", ROOT / "assets" / "stings" / "generate.py")
    assert spec and spec.loader


def test_stings_generate_script_is_deterministic(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("sting_gen", ROOT / "assets" / "stings" / "generate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sting_gen"] = module
    spec.loader.exec_module(module)
    module.main(tmp_path)
    assert (tmp_path / "chime-soft.wav").read_bytes() == (ROOT / "assets/stings/chime-soft.wav").read_bytes()
    assert abs(sf.info(tmp_path / "chime-bright.wav").duration - 1.0) < 0.01


def test_resolve_sting_builtin_relative_and_guards(tmp_path: Path) -> None:
    assert resolve_sting(None, tmp_path) is None
    assert resolve_sting("builtin:chime-soft", tmp_path).name == "chime-soft.wav"  # type: ignore[union-attr]
    (tmp_path / "mine.wav").write_bytes(b"x")
    assert resolve_sting("mine.wav", tmp_path) == (tmp_path / "mine.wav").resolve()
    for bad in ("../outside.wav", "/etc/passwd", "missing.wav", "builtin:nope", "builtin:../x", "builtin:"):
        with pytest.raises(MasteringError):
            resolve_sting(bad, tmp_path)


# --- ffmpeg wrapper ---


def test_master_ffmpeg_args_are_array_no_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    loud_json = b'{"input_i":"-20.1","input_tp":"-3.0","input_lra":"4.0","input_thresh":"-30.5","target_offset":"0.3"}'

    def fake_run(args: list[str], timeout: float = 600) -> bytes:
        return b" deesser  A->A\n"

    def fake_capture(args: list[str], *, timeout: float = 600) -> tuple[bytes, bytes]:
        calls.append(list(args))
        if args[-1] == "-" and "ebur128=peak=true" in args:
            return (
                b"",
                b"Summary:\n  Integrated loudness:\n    I:         -16.1 LUFS\n  True peak:\n    Peak:       -2.0 dBFS\n",
            )
        if args[-1] == "-":
            return b"", loud_json
        Path(args[-1]).write_bytes(b"data")
        if args[-1].endswith("mastered.wav"):
            sf.write(args[-1], np.full(4410, 0.2, dtype=np.float32), 44_100)
        return b"", b""

    monkeypatch.setattr(proc, "run", fake_run)
    monkeypatch.setattr(proc, "run_capture", fake_capture)
    ff.has_deesser.cache_clear()
    bed, intro = tmp_path / "bed.wav", tmp_path / "in.wav"
    out = tmp_path / "o.mp3"
    result = ff.master(
        AssembledTrack(samples=np.zeros(4410, dtype=np.float32)),
        out,
        intro=intro,
        outro=None,
        music_bed=bed,
        opus=True,
    )
    assert all(isinstance(a, str) for c in calls for a in c)
    assert all(c[0] == "ffmpeg" for c in calls)
    graph1 = next(c[c.index("-filter_complex") + 1] for c in calls if "-filter_complex" in c)
    assert "highpass=f=70" in graph1 and "deesser" in graph1 and "sidechaincompress" in graph1
    assert "print_format=json" in graph1 and "-stream_loop" in next(c for c in calls if "-stream_loop" in c)
    assert any("libmp3lame" in c and "128k" in c for c in calls)
    assert any("libopus" in c and "48k" in c for c in calls)
    assert result.loudness_lufs == -16.1 and result.true_peak_dbtp == -2.0
    assert result.opus_path == out.with_suffix(".opus") and out.exists() and result.opus_path.exists()
    ff.has_deesser.cache_clear()


def test_master_graph_variants_and_fallback_deesser() -> None:
    measured = Measured("-20", "-3", "4", "-30", "0.5")
    plain = build_filter_graph(
        has_intro=False, has_outro=False, has_bed=False, deesser="equalizer=f=6500", measured=measured
    )
    assert "concat" not in plain and "measured_I=-20" in plain and "linear=true" in plain
    both = build_filter_graph(has_intro=True, has_outro=True, has_bed=False, deesser="x", measured=None)
    assert "concat=n=5" in both and "d=0.25" in both


def test_master_failure_has_stderr_tail_and_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(args: list[str], *, timeout: float = 600) -> tuple[bytes, bytes]:
        raise subprocess.CalledProcessError(1, args, b"", b"\n".join(b"line%d" % i for i in range(30)))

    monkeypatch.setattr(proc, "run_capture", boom)
    monkeypatch.setattr(ff, "has_deesser", lambda: False)
    with pytest.raises(MasteringError) as info:
        ff.master(
            AssembledTrack(samples=np.zeros(100, dtype=np.float32)),
            tmp_path / "o.mp3",
            intro=None,
            outro=None,
            music_bed=None,
        )
    assert "line29" in str(info.value) and "line0" not in str(info.value)
    assert info.value.hint


def test_master_timeout_and_parse_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(args: list[str], *, timeout: float = 600) -> tuple[bytes, bytes]:
        raise subprocess.TimeoutExpired(args, 5)

    monkeypatch.setattr(proc, "run_capture", slow)
    with pytest.raises(MasteringError, match="timed out"):
        ff.measure_file(Path("x.mp3"))
    with pytest.raises(MasteringError):
        ff.parse_loudnorm_json(b"no json here")
    with pytest.raises(MasteringError):
        ff.parse_ebur128(b"nothing")


def test_has_deesser_detection_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    ff.has_deesser.cache_clear()
    monkeypatch.setattr(proc, "run", lambda *a, **k: b" T.. highpass\n")
    assert ff.has_deesser() is False
    ff.has_deesser.cache_clear()

    def missing(*a: object, **k: object) -> bytes:
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(proc, "run", missing)
    assert ff.has_deesser() is False
    ff.has_deesser.cache_clear()


def test_proc_run_capture_returns_both_streams() -> None:
    out, err = proc.run_capture([sys.executable, "-c", "import sys; print('o'); print('e', file=sys.stderr)"])
    assert out.strip() == b"o" and err.strip() == b"e"
    with pytest.raises(TypeError):
        proc.run_capture("echo hi")
    with pytest.raises(subprocess.CalledProcessError) as info:
        proc.run_capture([sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(2)"])
    assert b"bad" in info.value.stderr


# --- 5.13 tags ---


def _blank_mp3(path: Path) -> Path:
    path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    return path


def test_tags_id3_title_artist_album_date_written(tmp_path: Path) -> None:
    mp3 = _blank_mp3(tmp_path / "a.mp3")
    write_tags(mp3, title="T", artist="Ann", album="Alb", date="2026-11-02", cover=None)
    tags = ID3(mp3)
    assert (str(tags["TIT2"]), str(tags["TPE1"]), str(tags["TALB"]), str(tags["TDRC"])) == (
        "T",
        "Ann",
        "Alb",
        "2026-11-02",
    )
    assert not tags.getall("APIC")


def test_tags_cover_art_same_origin_under_1mb_embedded(tmp_path: Path) -> None:
    mp3 = _blank_mp3(tmp_path / "a.mp3")
    cover = fetch_cover("/img/c.png", "https://ex.com/post/1", lambda url: PNG)
    assert cover == PNG
    write_tags(mp3, title="T", artist="A", album="B", date="2026", cover=cover)
    apic = ID3(mp3).getall("APIC")[0]
    assert apic.mime == "image/png" and apic.type == 3 and apic.data == PNG
    write_tags(mp3, title="T", artist="A", album="B", date="2026", cover=JPEG)
    assert ID3(mp3).getall("APIC")[0].mime == "image/jpeg"
    write_tags(mp3, title="T", artist="A", album="B", date="2026", cover=b"junk")
    assert not ID3(mp3).getall("APIC")


def test_tags_cover_art_cross_origin_skipped() -> None:
    called: list[str] = []

    def fetcher(url: str) -> bytes:
        called.append(url)
        return PNG

    for img in (
        "https://cdn.other.com/c.png",
        "http://ex.com/c.png",
        "https://ex.com:8443/c.png",
        "ftp://ex.com/c.png",
    ):
        assert fetch_cover(img, "https://ex.com/p", fetcher) is None
    assert called == []
    assert fetch_cover("c.png", "not a url", fetcher) is None


def test_tags_cover_art_over_1mb_skipped() -> None:
    big = JPEG + b"\x00" * 1_048_576
    assert fetch_cover("/c.jpg", "https://ex.com/p", lambda url: big) is None
    assert fetch_cover("/c.jpg", "https://ex.com/p", lambda url: b"<html>") is None


def test_tags_cover_fetch_errors_are_swallowed() -> None:
    def fail(url: str) -> bytes:
        raise FetchError("nope", hint="h")

    assert fetch_cover("/c.jpg", "https://ex.com/p", fail) is None
    assert detect_image_mime(JPEG) == "image/jpeg" and detect_image_mime(b"") is None


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, follow_redirects=False)


def test_http_get_bytes_pins_ip_follows_redirect_and_blocks_private() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new.png"})
        if request.url.path == "/err":
            return httpx.Response(404)
        return httpx.Response(200, content=PNG)

    settings = Settings()
    resolver = lambda host: ["93.184.216.34"]  # noqa: E731
    data = http_get_bytes(
        "https://ex.com/old", settings, client=_client(httpx.MockTransport(handle)), resolver=resolver
    )
    assert data == PNG and seen[-1].url.host == "93.184.216.34" and seen[-1].headers["host"] == "ex.com"
    with pytest.raises(FetchError, match="404"):
        http_get_bytes(
            "https://ex.com/err", settings, client=_client(httpx.MockTransport(handle)), resolver=resolver
        )
    with pytest.raises(FetchError):
        http_get_bytes(
            "https://ex.com/a",
            settings,
            client=_client(httpx.MockTransport(handle)),
            resolver=lambda h: ["10.0.0.1"],
        )
    with pytest.raises(FetchError):
        http_get_bytes(
            "ftp://ex.com/a", settings, client=_client(httpx.MockTransport(handle)), resolver=resolver
        )
    with pytest.raises(FetchError, match="too large"):
        http_get_bytes(
            "https://ex.com/a",
            settings,
            max_bytes=10,
            client=_client(httpx.MockTransport(handle)),
            resolver=resolver,
        )


def test_http_get_bytes_redirect_loop_and_network_error() -> None:
    settings = Settings()
    resolver = lambda host: ["93.184.216.34"]  # noqa: E731
    loop = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(FetchError, match="redirects"):
        http_get_bytes("https://ex.com/a", settings, client=_client(loop), resolver=resolver)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(FetchError, match="Network error"):
        http_get_bytes(
            "https://ex.com/a", settings, client=_client(httpx.MockTransport(down)), resolver=resolver
        )
