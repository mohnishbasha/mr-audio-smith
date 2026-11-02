"""Mastering chain: clean, optional stings and music bed, two-pass loudnorm, encode (FR-014, ADR-008).

All ffmpeg calls go through audio_smith.proc as argument arrays.
"""

import json
import re
import subprocess
import tempfile
from functools import cache
from pathlib import Path

import soundfile as sf

from audio_smith import proc
from audio_smith.errors import MasteringError
from audio_smith.master.ffmpeg_graph import (
    DEESSER_FALLBACK,
    DEESSER_FILTER,
    TARGET_SAMPLE_RATE,
    Measured,
    build_filter_graph,
)
from audio_smith.master.peaks import compute_peaks
from audio_smith.paths import atomic_write
from audio_smith.pipeline_types import AssembledTrack, MasterResult

FFMPEG = "ffmpeg"
MP3_BITRATE = "128k"
OPUS_BITRATE = "48k"
OPUS_SAMPLE_RATE = 48_000
STDERR_TAIL_LINES = 12
BASE_ARGS = ("-hide_banner", "-nostdin", "-y")
_INTEGRATED = re.compile(r"^\s*I:\s+(-?\d+(?:\.\d+)?|-inf)\s+LUFS", re.MULTILINE)
_TRUE_PEAK = re.compile(r"True peak:\s*\n\s*Peak:\s+(-?\d+(?:\.\d+)?|-inf)\s+dBFS")
FFMPEG_HINT = "Check that ffmpeg is installed (run `audio-smith doctor`) and that the inputs are valid audio."


@cache
def has_deesser() -> bool:
    """Detect once whether this ffmpeg build ships the `deesser` filter."""
    try:
        out = proc.run([FFMPEG, "-hide_banner", "-filters"], timeout=30)
    except (subprocess.SubprocessError, OSError):
        return False
    return re.search(rb"\bdeesser\b", out) is not None


def _fail(what: str, error: BaseException) -> MasteringError:
    stderr = getattr(error, "stderr", b"") or b""
    tail = "\n".join(stderr.decode("utf-8", "replace").strip().splitlines()[-STDERR_TAIL_LINES:])
    if isinstance(error, subprocess.TimeoutExpired):
        tail = f"timed out after {error.timeout}s"
    return MasteringError(f"ffmpeg failed during {what}: {tail or error}", hint=FFMPEG_HINT)


def _ffmpeg(args: list[str], what: str, timeout_s: float) -> tuple[bytes, bytes]:
    try:
        return proc.run_capture([FFMPEG, *BASE_ARGS, *args], timeout=timeout_s)
    except (subprocess.SubprocessError, OSError) as e:
        raise _fail(what, e) from e


def _inputs(wav: Path, intro: Path | None, outro: Path | None, bed: Path | None) -> list[str]:
    args = ["-i", str(wav)]
    for path in (intro, outro):
        if path is not None:
            args += ["-i", str(path)]
    if bed is not None:
        args += ["-stream_loop", "-1", "-i", str(bed)]
    return args


def parse_loudnorm_json(stderr: bytes) -> Measured:
    """Extract the JSON block loudnorm prints at the end of its measuring pass."""
    text = stderr.decode("utf-8", "replace")
    start, end = text.rfind("{"), text.rfind("}")
    try:
        data = json.loads(text[start : end + 1])
        return Measured(
            input_i=str(data["input_i"]),
            input_tp=str(data["input_tp"]),
            input_lra=str(data["input_lra"]),
            input_thresh=str(data["input_thresh"]),
            target_offset=str(data["target_offset"]),
        )
    except (ValueError, KeyError) as e:
        raise MasteringError("Could not read the loudnorm measurement", hint=FFMPEG_HINT) from e


def parse_ebur128(stderr: bytes) -> tuple[float, float]:
    """Return (integrated LUFS, true peak dBTP) from the ebur128 summary block."""
    text = stderr.decode("utf-8", "replace")
    summary = text[text.rfind("Summary:") :] if "Summary:" in text else ""
    loud, peak = _INTEGRATED.search(summary), _TRUE_PEAK.search(summary)
    if loud is None or peak is None:
        raise MasteringError("Could not read the loudness measurement", hint=FFMPEG_HINT)
    return float(loud.group(1)), float(peak.group(1))


def measure_file(path: Path, timeout_s: float = 600) -> tuple[float, float]:
    """Measure integrated loudness and true peak with a separate ebur128 pass."""
    _, err = _ffmpeg(
        ["-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], "measurement", timeout_s
    )
    return parse_ebur128(err)


def _encode_args(src: Path, dst: Path, opus: bool) -> list[str]:
    if opus:
        rate, codec, bitrate = OPUS_SAMPLE_RATE, "libopus", OPUS_BITRATE
    else:
        rate, codec, bitrate = TARGET_SAMPLE_RATE, "libmp3lame", MP3_BITRATE
    return ["-i", str(src), "-vn", "-ac", "1", "-ar", str(rate), "-c:a", codec, "-b:a", bitrate, str(dst)]


def master(
    track: AssembledTrack,
    out_mp3: Path,
    *,
    intro: Path | None,
    outro: Path | None,
    music_bed: Path | None,
    opus: bool = False,
    timeout_s: float = 600,
) -> MasterResult:
    """Master an assembled track to -16 LUFS / -1.5 dBTP and encode MP3 (and optional Opus).

    Why two passes: single-pass loudnorm is dynamic and can pump; measuring first lets the
    second pass apply a linear gain that hits the target without altering dynamics.

    Raises:
        MasteringError: When any ffmpeg step fails, with the last stderr lines and a hint.
    """
    deesser = DEESSER_FILTER if has_deesser() else DEESSER_FALLBACK
    flags = {"has_intro": intro is not None, "has_outro": outro is not None, "has_bed": music_bed is not None}
    with tempfile.TemporaryDirectory(prefix="audio-smith-master-") as tmp_name:
        tmp = Path(tmp_name)
        voice, mastered, mp3_tmp = tmp / "voice.wav", tmp / "mastered.wav", tmp / "out.mp3"
        sf.write(voice, track.samples, track.sample_rate, subtype="FLOAT")
        inputs = _inputs(voice, intro, outro, music_bed)
        graph1 = build_filter_graph(deesser=deesser, measured=None, **flags)
        _, err = _ffmpeg(
            [*inputs, "-filter_complex", graph1, "-map", "[out]", "-f", "null", "-"],
            "loudness measurement",
            timeout_s,
        )
        graph2 = build_filter_graph(deesser=deesser, measured=parse_loudnorm_json(err), **flags)
        _ffmpeg(
            [*inputs, "-filter_complex", graph2, "-map", "[out]", "-c:a", "pcm_f32le", str(mastered)],
            "loudness normalization",
            timeout_s,
        )
        _ffmpeg(_encode_args(mastered, mp3_tmp, opus=False), "mp3 encode", timeout_s)
        atomic_write(out_mp3, mp3_tmp.read_bytes())
        opus_path = _write_opus(mastered, tmp, out_mp3, timeout_s) if opus else None
        data, rate = sf.read(mastered, dtype="float32")
        lufs, tp = measure_file(out_mp3, timeout_s)
    return MasterResult(
        path=out_mp3,
        duration_s=round(len(data) / rate, 3),
        loudness_lufs=lufs,
        true_peak_dbtp=tp,
        peaks=compute_peaks(data),
        opus_path=opus_path,
    )


def _write_opus(src: Path, tmp: Path, out_mp3: Path, timeout_s: float) -> Path:
    target = out_mp3.with_suffix(".opus")
    staged = tmp / "out.opus"
    _ffmpeg(_encode_args(src, staged, opus=True), "opus encode", timeout_s)
    atomic_write(target, staged.read_bytes())
    return target
