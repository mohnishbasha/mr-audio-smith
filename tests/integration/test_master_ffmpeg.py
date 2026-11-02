"""Real-ffmpeg mastering tests (TEST_PLAN 5.12)."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from audio_smith.master.ffmpeg import master
from audio_smith.master.stings import resolve_sting
from audio_smith.pipeline_types import MASTER_SAMPLE_RATE, AssembledTrack

pytestmark = pytest.mark.integration

TRACK_SECONDS = 6
LUFS_TARGET = -16.0
LUFS_TOLERANCE = 1.0
TP_LIMIT = -1.5
TP_TOLERANCE = 0.2


def _speechlike_track() -> AssembledTrack:
    """Amplitude-modulated tones (about 4 Hz syllables) standing in for speech."""
    t = np.arange(TRACK_SECONDS * MASTER_SAMPLE_RATE) / MASTER_SAMPLE_RATE
    carrier = np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 880 * t)
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 4 * t))
    samples = (0.2 * carrier * envelope).astype(np.float32)
    return AssembledTrack(samples=samples)


def _probe(path: Path) -> dict[str, object]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True,
        capture_output=True,
    ).stdout
    result: dict[str, object] = json.loads(out)
    return result


@pytest.fixture(scope="module")
def mastered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("master") / "plain.mp3"
    master(_speechlike_track(), out, intro=None, outro=None, music_bed=None, opus=True)
    return out


def test_master_loudness_within_target(mastered: Path) -> None:
    from audio_smith.master.ffmpeg import measure_file

    lufs, tp = measure_file(mastered)
    assert abs(lufs - LUFS_TARGET) <= LUFS_TOLERANCE
    assert tp <= TP_LIMIT + TP_TOLERANCE


def it_master_true_peak_at_or_below_minus_1_5_dbtp(tmp_path: Path) -> None:
    result = master(_speechlike_track(), tmp_path / "a.mp3", intro=None, outro=None, music_bed=None)
    assert result.true_peak_dbtp <= TP_LIMIT + TP_TOLERANCE
    assert abs(result.loudness_lufs - LUFS_TARGET) <= LUFS_TOLERANCE
    assert len(result.peaks) == 28


def it_master_mp3_128k_mono_44100_default(mastered: Path) -> None:
    stream = _probe(mastered)["streams"][0]  # type: ignore[index]
    assert stream["codec_name"] == "mp3"
    assert stream["channels"] == 1
    assert stream["sample_rate"] == "44100"
    assert abs(int(stream["bit_rate"]) - 128_000) < 8_000


def it_master_opus_optional_output_created(mastered: Path) -> None:
    opus = mastered.with_suffix(".opus")
    assert opus.exists()
    assert _probe(opus)["streams"][0]["codec_name"] == "opus"  # type: ignore[index]


def it_master_intro_outro_stings_included(mastered: Path, tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    intro, outro = resolve_sting("builtin:chime-soft", root), resolve_sting("builtin:chime-bright", root)
    out = tmp_path / "stings.mp3"
    master(_speechlike_track(), out, intro=intro, outro=outro, music_bed=None)
    plain = float(_probe(mastered)["format"]["duration"])  # type: ignore[index]
    with_stings = float(_probe(out)["format"]["duration"])  # type: ignore[index]
    expected_extra = 1.2 + 1.0 + 2 * 0.25
    assert abs((with_stings - plain) - expected_extra) < 0.15


def it_master_music_bed_ducks_under_voice(mastered: Path, tmp_path: Path) -> None:
    t = np.arange(2 * MASTER_SAMPLE_RATE) / MASTER_SAMPLE_RATE
    bed = tmp_path / "bed.wav"
    import soundfile as sf

    sf.write(bed, (0.3 * np.sin(2 * np.pi * 110 * t)).astype(np.float32), MASTER_SAMPLE_RATE)
    out = tmp_path / "bed.mp3"
    result = master(_speechlike_track(), out, intro=None, outro=None, music_bed=bed)
    plain = float(_probe(mastered)["format"]["duration"])  # type: ignore[index]
    assert abs(float(_probe(out)["format"]["duration"]) - plain) < 0.2  # type: ignore[index]
    assert abs(result.loudness_lufs - LUFS_TARGET) <= LUFS_TOLERANCE


def it_master_two_pass_loudnorm_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from audio_smith import proc

    graphs: list[str] = []
    real = proc.run_capture

    def spy(args: list[str], *, timeout: float = 600) -> tuple[bytes, bytes]:
        if "-filter_complex" in args:
            graphs.append(args[args.index("-filter_complex") + 1])
        return real(args, timeout=timeout)

    monkeypatch.setattr(proc, "run_capture", spy)
    master(_speechlike_track(), tmp_path / "t.mp3", intro=None, outro=None, music_bed=None)
    assert len(graphs) == 2
    assert "print_format=json" in graphs[0]
    assert "measured_I=" in graphs[1] and "linear=true" in graphs[1]
