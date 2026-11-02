"""Filter-graph construction for the mastering chain (pure functions, no subprocesses)."""

from dataclasses import dataclass

TARGET_SAMPLE_RATE = 44_100
DEFAULT_TARGET_LUFS = -16.0
DEFAULT_TRUE_PEAK = -1.5
DEFAULT_LRA = 11.0
HIGHPASS_HZ = 70
DEESSER_FILTER = "deesser=i=0.4:m=0.5:f=0.5"
DEESSER_FALLBACK = "equalizer=f=6500:width_type=q:w=3:g=-3"
COMPRESSOR = "acompressor=threshold=-18dB:ratio=2.5:attack=15:release=200"
STING_GAP_S = 0.25
MUSIC_BED_DB = -24
DUCK_FILTER = "sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300"
MONO_FORMAT = "aformat=sample_fmts=fltp:channel_layouts=mono"


@dataclass(frozen=True)
class Measured:
    """Values from loudnorm's first (measuring) pass."""

    input_i: str
    input_tp: str
    input_lra: str
    input_thresh: str
    target_offset: str


def loudnorm_filter(measured: Measured | None) -> str:
    """First pass prints JSON; second pass applies the measured values linearly."""
    base = f"loudnorm=I={DEFAULT_TARGET_LUFS}:TP={DEFAULT_TRUE_PEAK}:LRA={DEFAULT_LRA}"
    if measured is None:
        return f"{base}:print_format=json"
    return (
        f"{base}:measured_I={measured.input_i}:measured_TP={measured.input_tp}"
        f":measured_LRA={measured.input_lra}:measured_thresh={measured.input_thresh}"
        f":offset={measured.target_offset}:linear=true:print_format=summary"
    )


def _normalize(label_in: str, label_out: str) -> str:
    return f"[{label_in}]aresample={TARGET_SAMPLE_RATE},{MONO_FORMAT}[{label_out}]"


def build_filter_graph(
    *, has_intro: bool, has_outro: bool, has_bed: bool, deesser: str, measured: Measured | None
) -> str:
    """Voice cleanup, optional stings and ducked bed, then loudnorm.

    Input indexes: 0 voice, then intro, outro, bed (each only if present).
    """
    parts = [
        f"[0:a]highpass=f={HIGHPASS_HZ},{deesser},{COMPRESSOR},aresample={TARGET_SAMPLE_RATE},{MONO_FORMAT}[v]"
    ]
    segments = ["[v]"]
    index = 1
    if has_intro:
        parts.append(_normalize(f"{index}:a", "intro"))
        parts.append(f"anullsrc=r={TARGET_SAMPLE_RATE}:cl=mono:d={STING_GAP_S}[gi]")
        segments = ["[intro]", "[gi]", "[v]"]
        index += 1
    if has_outro:
        parts.append(_normalize(f"{index}:a", "outro"))
        parts.append(f"anullsrc=r={TARGET_SAMPLE_RATE}:cl=mono:d={STING_GAP_S}[go]")
        segments += ["[go]", "[outro]"]
        index += 1
    if len(segments) > 1:
        parts.append(f"{''.join(segments)}concat=n={len(segments)}:v=0:a=1[body]")
    else:
        parts.append("[v]anull[body]")
    last = "body"
    if has_bed:
        parts += [
            "[body]asplit=2[vm][vs]",
            f"[{index}:a]aresample={TARGET_SAMPLE_RATE},{MONO_FORMAT},volume={MUSIC_BED_DB}dB[bed]",
            f"[bed][vs]{DUCK_FILTER}[ducked]",
            "[vm][ducked]amix=inputs=2:duration=first:normalize=0[mix]",
        ]
        last = "mix"
    parts.append(f"[{last}]{loudnorm_filter(measured)},aresample={TARGET_SAMPLE_RATE}[out]")
    return ";".join(parts)
