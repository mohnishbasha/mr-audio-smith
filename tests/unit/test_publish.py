"""Tests for WebVTT captions, manifest, and published schemas (TEST_PLAN 5.14, 5.15)."""

import itertools
import json
import re
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from audio_smith.pipeline_types import ChunkSpan
from audio_smith.publish.manifest import (
    BackendRef,
    ChunkRecord,
    Manifest,
    ProfileRef,
    Timings,
    Track,
    load_manifest,
    write_manifest,
)
from audio_smith.publish.schemas import export_all
from audio_smith.publish.vtt import (
    LONG_SENTENCE_CHARS,
    build_cues,
    format_timestamp,
    render_vtt,
    split_sentences,
    write_vtt,
)

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
SPANS = [
    ChunkSpan(
        chunk_id="001",
        start_ms=0,
        end_ms=4000,
        text="My dear Aadi... [pause 600] Some days feel big! Do you see *it*?",
    ),
    ChunkSpan(chunk_id="002", start_ms=4500, end_ms=6500, text="Dr. Rao met Mr. Lee, e.g. today."),
]


def test_vtt_one_cue_per_sentence() -> None:
    cues = build_cues([SPANS[0]])
    assert [c.text for c in cues] == ["My dear Aadi...", "Some days feel big!", "Do you see it?"]


def test_vtt_abbreviations_stay_intact() -> None:
    assert split_sentences("Dr. Rao met Mr. Lee, e.g. today. Fine.") == [
        "Dr. Rao met Mr. Lee, e.g. today.",
        "Fine.",
    ]
    assert len(build_cues([SPANS[1]])) == 1


def test_vtt_cues_align_within_150ms() -> None:
    cues = build_cues(SPANS)
    for span in SPANS:
        inside = [c for c in cues if span.start_ms <= c.start_ms and c.end_ms <= span.end_ms]
        assert abs(inside[0].start_ms - span.start_ms) <= 150
        assert abs(inside[-1].end_ms - span.end_ms) <= 150


def test_vtt_text_from_narrated_script_not_page() -> None:
    span = ChunkSpan(chunk_id="001", start_ms=0, end_ms=1000, text="Narrated words only.")
    assert [c.text for c in build_cues([span])] == ["Narrated words only."]


def test_vtt_distribution_by_character_length_proportion() -> None:
    span = ChunkSpan(chunk_id="001", start_ms=0, end_ms=4000, text="Aaaaaaa. " + "B" * 20 + ".")
    first, second = build_cues([span])
    assert first.end_ms == second.start_ms == round(4000 * 8 / 29)
    assert second.end_ms == 4000


def test_vtt_format_valid_header_and_timestamps() -> None:
    out = render_vtt(build_cues(SPANS))
    assert out.startswith("WEBVTT\n\n")
    stamps = re.findall(r"(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})", out)
    assert len(stamps) == 4
    assert stamps == sorted(stamps)
    assert format_timestamp(3_723_004) == "01:02:03.004"


def test_vtt_cues_monotonic_and_non_overlapping() -> None:
    cues = build_cues(SPANS)
    for a, b in itertools.pairwise(cues):
        assert a.start_ms <= a.end_ms <= b.start_ms
    for cue in cues:
        assert any(s.start_ms <= cue.start_ms and cue.end_ms <= s.end_ms for s in SPANS)


def test_vtt_pause_markers_not_rendered_as_text() -> None:
    out = render_vtt(build_cues(SPANS))
    assert "[pause" not in out and "*" not in out


def test_vtt_escapes_markup() -> None:
    span = ChunkSpan(chunk_id="001", start_ms=0, end_ms=1000, text="Tom & Jerry <b> > ok.")
    out = render_vtt(build_cues([span]))
    assert "Tom &amp; Jerry &lt;b&gt; &gt; ok." in out


def test_vtt_long_sentence_split_at_comma() -> None:
    text = ("word " * 14).strip() + ", " + ("more " * 14).strip() + "."
    assert len(text) > LONG_SENTENCE_CHARS
    span = ChunkSpan(chunk_id="001", start_ms=0, end_ms=2000, text=text)
    assert len(build_cues([span])) == 2
    nocomma = ChunkSpan(chunk_id="001", start_ms=0, end_ms=2000, text="word " * 30 + "end.")
    assert len(build_cues([nocomma])) == 1


def test_vtt_empty_text_yields_no_cues_and_write(tmp_path: Path) -> None:
    empty = ChunkSpan(chunk_id="001", start_ms=0, end_ms=500, text="[pause 500]")
    assert build_cues([empty]) == []
    path = write_vtt(tmp_path / "a.en.vtt", SPANS)
    assert path.read_text(encoding="utf-8").startswith("WEBVTT")


def _manifest() -> Manifest:
    return Manifest(
        tool_version="0.3.0",
        source="https://example.com/p.html",
        title="T",
        profile=ProfileRef(id="kid-5", version="1.0.0"),
        backend=BackendRef(id="maya2", model="maya-2"),
        llm="ollama/qwen3:14b",
        voice_id="dad",
        content_hash="abc123",
        created_at="2026-11-02T10:00:00Z",
        approved=True,
        tracks=[
            Track(
                lang="en",
                kind="main",
                file="p.en.mp3",
                duration_s=12.5,
                loudness_lufs=-16.0,
                true_peak_dbtp=-1.5,
                peaks=[0.0, 0.5, 1.0],
                captions="p.en.vtt",
            )
        ],
        chunks=[ChunkRecord(id="001", hash="h", take=0, seed=7, duration_ms=4000)],
        timings=Timings(synth=3.2),
        warnings=["QA skipped", "non-commercial weights"],
    )


def test_manifest_validates_against_published_schema() -> None:
    schema = json.loads((SCHEMAS / "manifest.schema.json").read_text(encoding="utf-8"))
    data = json.loads(_manifest().model_dump_json(by_alias=True))
    jsonschema.validate(data, schema)
    data["extra"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_manifest_round_trip_and_fields(tmp_path: Path) -> None:
    path = write_manifest(tmp_path / "p.manifest.json", _manifest())
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == "audio-smith/manifest@1"
    assert raw["approved"] is True and raw["voice_id"] == "dad"
    assert raw["chunks"][0]["similarity"] is None
    assert set(raw["timings"]) == {"fetch", "extract", "script", "synth", "master", "publish"}
    assert load_manifest(path) == _manifest()


def test_manifest_rejects_bad_input() -> None:
    data = json.loads(_manifest().model_dump_json(by_alias=True))
    with pytest.raises(ValidationError):
        Manifest.model_validate({**data, "reference": "reference.wav"})
    with pytest.raises(ValidationError):
        Manifest.model_validate({**data, "created_at": "yesterday"})
    data["tracks"][0]["peaks"] = [1.5]
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_manifest_has_no_secrets_clips_or_consent(tmp_path: Path) -> None:
    text = write_manifest(tmp_path / "m.json", _manifest()).read_text(encoding="utf-8").lower()
    for forbidden in ("reference.wav", "statement", "api_key", "token", "consent"):
        assert forbidden not in text


def test_manifest_schemas_published_are_current(tmp_path: Path) -> None:
    for path in export_all(tmp_path):
        published = SCHEMAS / path.name
        assert published.read_text(encoding="utf-8") == path.read_text(encoding="utf-8"), path.name
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["$id"] == f"https://getaudiosmith.com/schemas/{path.name}"
        assert doc["title"]
