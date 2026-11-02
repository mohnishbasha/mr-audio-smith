import threading
import time
from pathlib import Path

import numpy as np
import pytest

from audio_smith.cache import CacheStore
from audio_smith.errors import ConsentError, SynthesisError
from audio_smith.pipeline_types import SynthUnit
from audio_smith.script.markdown import Chunk, Script, ScriptMeta
from audio_smith.tts.base import PcmAudio, SynthParams, VoiceRef
from audio_smith.tts.mock import MockBackend
from audio_smith.tts.planner import plan_units
from audio_smith.tts.runner import ProgressEvent, SynthesisRunner, rich_progress

VOICE = VoiceRef(id="mock-a", builtin=True)


def make_script(*texts: str) -> Script:
    meta = ScriptMeta(source="s", profile="p", content_hash="h", generated_by="t")
    return Script(meta=meta, chunks=[Chunk(number=i + 1, text=t) for i, t in enumerate(texts)])


def plan(script: Script, **kw: object) -> list[SynthUnit]:
    args: dict[str, object] = {
        "max_chars": 400,
        "lexicon": {},
        "backend_id": "mock",
        "model": "m",
        "voice": VOICE,
        "rate": 1.0,
    }
    args.update(kw)
    return plan_units(script, **args).units  # type: ignore[arg-type]


def units_for(n: int) -> list[SynthUnit]:
    return plan(make_script(*[f"Sentence number {i} here." for i in range(n)]))


def runner(cache: CacheStore, backend: object | None = None, **kw: object) -> SynthesisRunner:
    return SynthesisRunner(backend or MockBackend(), VOICE, SynthParams(), cache, **kw)  # type: ignore[arg-type]


class CountingBackend(MockBackend):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        self.calls.append(text)
        return super().synth(text, voice, params)


def test_planner_split_on_pause_markers_into_segments() -> None:
    units = plan(make_script("Hello there. [pause 500] And *this* matters. [pause 300] End."))
    assert [u.text for u in units] == ["Hello there.", "And this matters.", "End."]
    assert [u.pause_after_ms for u in units] == [500, 300, 0]
    assert [u.index for u in units] == [0, 1, 2]


def test_planner_pause_only_chunk_extends_previous_unit() -> None:
    units = plan(make_script("Hi there.", "[pause 700]"))
    assert len(units) == 1 and units[0].pause_after_ms == 700


def test_planner_max_chars_splits_on_sentence_boundary() -> None:
    result = plan_units(
        make_script("One is here. Two is here. Three is here."),
        max_chars=25,
        lexicon={},
        backend_id="b",
        model="m",
        voice=VOICE,
        rate=1.0,
    )
    assert [u.text for u in result.units] == ["One is here. Two is here.", "Three is here."]
    assert result.warnings == []


def test_planner_oversized_sentence_split_at_comma_with_warning() -> None:
    result = plan_units(
        make_script("Alpha beta gamma, delta epsilon zeta eta theta."),
        max_chars=20,
        lexicon={},
        backend_id="b",
        model="m",
        voice=VOICE,
        rate=1.0,
    )
    assert result.units[0].text == "Alpha beta gamma,"
    assert all(len(u.text) <= 20 for u in result.units)
    assert len(result.warnings) == 1 and "001" in result.warnings[0]


def test_planner_oversized_word_without_break_still_bounded() -> None:
    result = plan_units(
        make_script("x" * 50), max_chars=20, lexicon={}, backend_id="b", model="m", voice=VOICE, rate=1.0
    )
    assert [len(u.text) for u in result.units] == [20, 20, 10]


def test_planner_lexicon_applied_before_keying() -> None:
    plain = plan(make_script("Aadi runs."))[0]
    lex = plan(make_script("Aadi runs."), lexicon={"Aadi": "AH-dee"})[0]
    assert lex.text == "AH-dee runs." and lex.display_text == "Aadi runs."
    assert lex.key != plain.key


def test_planner_chunk_key_stable_across_runs() -> None:
    s = make_script("Same text.")
    assert plan(s)[0].key == plan(s)[0].key


def test_planner_chunk_key_changes_with_voice_seed_rate() -> None:
    s = make_script("Same text.")
    base = plan(s)[0].key
    other_voice = plan(s, voice=VoiceRef(id="mock-b"))[0].key
    assert len({base, other_voice, plan(s, seed_base=1)[0].key, plan(s, rate=1.1)[0].key}) == 4


def test_runner_chunks_subset_renders_only_selected() -> None:
    s = make_script("One.", "Two.", "Three.")
    assert [u.chunk_id for u in plan(s, chunks={"002", "003"})] == ["002", "003"]


def test_runner_cache_hit_skips_synthesis(tmp_path: Path) -> None:
    backend, cache, units = CountingBackend(), CacheStore(tmp_path), units_for(2)
    first = runner(cache, backend).run(units)
    second = runner(cache, backend).run(units)
    assert len(backend.calls) == 2
    assert [r.cached for r in first] == [False, False]
    assert [r.cached for r in second] == [True, True]
    assert np.allclose(first[0].samples, second[0].samples, atol=1e-6)


def test_runner_corrupt_cache_entry_is_resynthesized(tmp_path: Path) -> None:
    cache, units = CacheStore(tmp_path), units_for(1)
    cache.put_bytes("chunks", units[0].key, "wav", b"garbage")
    assert runner(cache).run(units)[0].cached is False


class Flaky(MockBackend):
    def __init__(self, failures: int, exc: Exception) -> None:
        self.failures, self.exc, self.calls = failures, exc, 0

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return super().synth(text, voice, params)


def test_runner_failed_chunk_retried_twice_with_backoff(tmp_path: Path) -> None:
    sleeps: list[float] = []
    backend = Flaky(2, SynthesisError("boom"))
    out = runner(CacheStore(tmp_path), backend, sleep=sleeps.append, backoff_s=1.0).run(units_for(1))
    assert backend.calls == 3 and len(out) == 1
    assert 1.0 <= sleeps[0] <= 1.25 and 2.0 <= sleeps[1] <= 2.5


def test_runner_third_failure_marks_chunk_failed(tmp_path: Path) -> None:
    backend = Flaky(99, RuntimeError("net"))
    with pytest.raises(SynthesisError, match="chunk 001"):
        runner(CacheStore(tmp_path), backend, sleep=lambda _s: None).run(units_for(1))
    assert backend.calls == 3


def test_runner_consent_error_not_retried(tmp_path: Path) -> None:
    backend = Flaky(99, ConsentError("no consent"))
    with pytest.raises(ConsentError):
        runner(CacheStore(tmp_path), backend, sleep=lambda _s: None).run(units_for(1))
    assert backend.calls == 1


def test_runner_non_retryable_synthesis_error_fails_fast(tmp_path: Path) -> None:
    err = SynthesisError("bad input")
    err.retryable = False  # type: ignore[attr-defined]
    backend = Flaky(99, err)
    with pytest.raises(SynthesisError):
        runner(CacheStore(tmp_path), backend, sleep=lambda _s: None).run(units_for(1))
    assert backend.calls == 1


class InterruptOnThird(CountingBackend):
    def __init__(self) -> None:
        super().__init__()
        self.armed = True

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        if self.armed and len(self.calls) == 2:
            raise KeyboardInterrupt
        return super().synth(text, voice, params)


def test_runner_resume_after_interrupt_renders_only_remainder(tmp_path: Path) -> None:
    backend, cache, units = InterruptOnThird(), CacheStore(tmp_path), units_for(5)
    with pytest.raises(KeyboardInterrupt):
        runner(cache, backend).run(units)
    backend.armed = False
    backend.calls.clear()
    out = runner(cache, backend).run(units)
    assert [r.cached for r in out] == [True, True, False, False, False]
    assert len(backend.calls) == 3


def test_runner_cache_write_atomic_temp_rename(tmp_path: Path) -> None:
    cache, units = CacheStore(tmp_path), units_for(2)
    seen: list[bool] = []

    class Probe(MockBackend):
        def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
            seen.append(any(cache.base.glob("chunks/*.tmp")))
            return super().synth(text, voice, params)

    runner(cache, Probe()).run(units)
    assert seen == [False, False]
    assert not list(cache.base.glob("chunks/.*tmp")) and len(list(cache.base.glob("chunks/*.wav"))) == 2


def test_runner_failure_keeps_completed_units_cached(tmp_path: Path) -> None:
    cache, units = CacheStore(tmp_path), units_for(3)

    class FailsSecond(MockBackend):
        def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
            if text == units[1].text:
                raise RuntimeError("down")
            return super().synth(text, voice, params)

    with pytest.raises(SynthesisError, match="chunk 002"):
        runner(cache, FailsSecond(), retries=0).run(units)
    assert cache.exists("chunks", units[0].key, "wav")


def test_runner_concurrency_bounded_semaphore_default_2(tmp_path: Path) -> None:
    lock, state = threading.Lock(), {"now": 0, "peak": 0}

    class Slow(MockBackend):
        def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.02)
            with lock:
                state["now"] -= 1
            return super().synth(text, voice, params)

    units = units_for(8)
    out = runner(CacheStore(tmp_path), Slow(), concurrency=2).run(units)
    assert state["peak"] == 2
    assert [r.unit.key for r in out] == [u.key for u in units]


def test_runner_progress_events_reported(tmp_path: Path) -> None:
    events: list[ProgressEvent] = []
    runner(CacheStore(tmp_path), progress=events.append, concurrency=2).run(units_for(3))
    assert sorted(e.done for e in events) == [1, 2, 3] and events[0].total == 3


def test_rich_progress_callback_runs_to_completion() -> None:
    cb = rich_progress()
    cb(ProgressEvent(stage="synth", done=1, total=2, chunk_id="001"))
    cb(ProgressEvent(stage="synth", done=2, total=2, chunk_id="002"))
