import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from audio_smith.cache import CacheStore
from audio_smith.pipeline_types import SynthUnit
from audio_smith.qa.loudness import SILENCE_DBFS, measure_rms_dbfs
from audio_smith.qa.similarity import (
    DEFAULT_THRESHOLD,
    ResemblyzerEmbedder,
    SimilarityQA,
    cosine,
    load_embedder,
)
from audio_smith.tts.base import FloatArray, PcmAudio, SynthParams, VoiceRef
from audio_smith.tts.mock import MockBackend
from audio_smith.tts.runner import SynthesisRunner

VOICE = VoiceRef(id="mock-a", builtin=True)


class StubEmbedder:
    """Maps a sample's first value to a unit vector so tests pick similarities by seed."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, samples: FloatArray, sample_rate: int) -> np.ndarray[Any, Any]:
        self.calls += 1
        angle = float(samples[0]) * np.pi / 2
        return np.array([np.cos(angle), np.sin(angle)])


class SeededBackend(MockBackend):
    """First sample encodes how far the take is from the reference, by seed."""

    def __init__(self, offsets: dict[int, float]) -> None:
        self.offsets, self.seeds = offsets, []

    seeds: list[int | None]  # type: ignore[assignment]

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        self.seeds.append(params.seed)
        samples = np.full(2400, self.offsets.get(params.seed or 0, 0.0), dtype=np.float32)
        return PcmAudio(samples=samples, sample_rate=24_000)


def unit(key: str = "k1", chunk: str = "001") -> SynthUnit:
    return SynthUnit(chunk_id=chunk, index=0, text="Hello there.", display_text="Hello there.", key=key)


def make(
    tmp_path: Path, offsets: dict[int, float], takes: int = 2, threshold: float = 0.75
) -> tuple[SynthesisRunner, SeededBackend, StubEmbedder]:
    emb, backend = StubEmbedder(), SeededBackend(offsets)
    qa = SimilarityQA(emb, np.array([1.0, 0.0]), threshold, takes)
    return SynthesisRunner(backend, VOICE, SynthParams(), CacheStore(tmp_path), qa=qa), backend, emb


def test_qa_default_threshold_0_75() -> None:
    assert DEFAULT_THRESHOLD == 0.75


def test_qa_similarity_below_threshold_rerenders(tmp_path: Path) -> None:
    r, backend, _ = make(tmp_path, {0: 0.9, 1: 0.0})
    out = r.run([unit()])[0]
    assert backend.seeds == [0, 1] and out.take == 1 and out.similarity == pytest.approx(1.0)


def test_qa_good_first_take_not_rerendered(tmp_path: Path) -> None:
    r, backend, _ = make(tmp_path, {0: 0.0})
    out = r.run([unit()])[0]
    assert backend.seeds == [0] and out.take == 0


def test_qa_rerender_uses_new_seed_each_take(tmp_path: Path) -> None:
    r, backend, _ = make(tmp_path, {0: 0.9, 1: 0.8, 2: 0.7}, takes=3)
    r.run([unit()])
    assert backend.seeds == [0, 1, 2]


def test_qa_takes_per_chunk_limit_respected(tmp_path: Path) -> None:
    r, backend, _ = make(tmp_path, {0: 0.9, 1: 0.9, 2: 0.9, 3: 0.9}, takes=3)
    r.run([unit()])
    assert len(backend.seeds) == 3


def test_qa_best_take_kept_by_score(tmp_path: Path) -> None:
    r, _, _ = make(tmp_path, {0: 0.9, 1: 0.5, 2: 0.7}, takes=3)
    out = r.run([unit()])[0]
    assert out.take == 1 and out.seed == 1 and out.samples[0] == pytest.approx(0.5)


def test_qa_takes_cached_separately_and_scores_not_recomputed(tmp_path: Path) -> None:
    r, backend, emb = make(tmp_path, {0: 0.9, 1: 0.0})
    r.run([unit()])
    cache = CacheStore(tmp_path)
    assert len(list(cache.base.glob("takes/*.wav"))) == 1 and (cache.base / "takes/k1.json").is_file()
    embeds = emb.calls
    again = r.run([unit()])[0]
    assert emb.calls == embeds and backend.seeds == [0, 1]
    assert again.cached and again.take == 1 and again.similarity == pytest.approx(1.0)


def test_qa_cached_unit_without_score_is_rescored(tmp_path: Path) -> None:
    plain = SynthesisRunner(SeededBackend({}), VOICE, SynthParams(), CacheStore(tmp_path))
    plain.run([unit()])
    r, backend, emb = make(tmp_path, {})
    out = r.run([unit()])[0]
    assert backend.seeds == [] and emb.calls == 1 and out.cached and out.similarity is not None


def test_qa_builtin_voice_compared_to_chunk_1(tmp_path: Path) -> None:
    emb, backend = StubEmbedder(), SeededBackend({0: 0.2, 1: 0.2})
    qa = SimilarityQA.reference_from_first(emb, threshold=0.75, takes_per_chunk=1)
    r = SynthesisRunner(backend, VOICE, SynthParams(), CacheStore(tmp_path), concurrency=2, qa=qa)
    out = r.run([unit("a", "001"), unit("b", "002")])
    assert out[0].similarity == 1.0 and out[1].similarity == pytest.approx(1.0)
    assert qa.reference is not None and not qa.needs_reference


def test_qa_from_reference_clip_embeds_once() -> None:
    emb = StubEmbedder()
    qa = SimilarityQA.from_reference_clip(emb, np.zeros(10, dtype=np.float32), 24_000)
    assert emb.calls == 1 and qa.acceptable(0.75) and not qa.acceptable(0.7)


def test_qa_report_lists_scores_per_chunk(tmp_path: Path) -> None:
    r, _, _ = make(tmp_path, {0: 0.0})
    out = r.run([unit("a", "001"), unit("b", "002")])
    assert {o.unit.chunk_id: o.similarity for o in out} == {"001": 1.0, "002": 1.0}


def test_qa_extra_missing_skips_with_manifest_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "resemblyzer", None)
    assert load_embedder() is None


def test_qa_resemblyzer_embedder_uses_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        class VoiceEncoder:
            def embed_utterance(self, wav: object) -> list[float]:
                return [1.0, 2.0]

        @staticmethod
        def preprocess_wav(samples: object, source_sr: int) -> object:
            return samples

    monkeypatch.setitem(sys.modules, "resemblyzer", Fake)
    emb = load_embedder()
    assert isinstance(emb, ResemblyzerEmbedder)
    assert list(emb.embed(np.zeros(4, dtype=np.float32), 16_000)) == [1.0, 2.0]


def test_qa_cosine() -> None:
    assert cosine(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(1.0)
    assert cosine(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(0.0)
    assert cosine(np.zeros(2), np.array([1.0, 0.0])) == 0.0


def test_measure_rms_dbfs() -> None:
    assert measure_rms_dbfs(np.full(100, 0.5, dtype=np.float32)) == pytest.approx(-6.02, abs=0.01)
    assert measure_rms_dbfs(np.zeros(10, dtype=np.float32)) == SILENCE_DBFS
    assert measure_rms_dbfs(np.zeros(0, dtype=np.float32)) == SILENCE_DBFS
