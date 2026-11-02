"""Synthesis runner (FR-012, NFR-005): cache, retries, resume, concurrency, QA takes.

Why: a long narration must survive Ctrl-C and flaky backends. Every finished unit is written
atomically to the cache before the next starts, so a re-run renders only the remainder.
"""

import io
import json
import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

import soundfile as sf
from pydantic import BaseModel
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeRemainingColumn

from audio_smith.cache.keys import chunk_key
from audio_smith.cache.store import CacheStore
from audio_smith.errors import ConsentError, SynthesisError, UsageError
from audio_smith.pipeline_types import RenderedUnit, SynthUnit
from audio_smith.qa.similarity import SimilarityQA
from audio_smith.tts.base import FloatArray, PcmAudio, SynthParams, TTSBackend, VoiceRef

DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_S = 0.5
JITTER_FRACTION = 0.25
WAV_SUBTYPE = "FLOAT"
_NO_RETRY = (ConsentError, UsageError)


class ProgressEvent(BaseModel):
    stage: str
    done: int
    total: int
    chunk_id: str
    cached: bool = False


class _Take(BaseModel):
    """Score record stored next to the cached WAV so unchanged re-runs skip embedding."""

    take: int
    seed: int
    similarity: float
    key: str


def _encode_wav(samples: FloatArray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype=WAV_SUBTYPE)
    return buf.getvalue()


def _decode_wav(data: bytes) -> tuple[FloatArray, int]:
    samples, rate = sf.read(io.BytesIO(data), dtype="float32")
    return samples, int(rate)


class SynthesisRunner:
    def __init__(
        self,
        backend: TTSBackend,
        voice: VoiceRef,
        params: SynthParams,
        cache: CacheStore,
        *,
        retries: int = DEFAULT_RETRIES,
        backoff_s: float = DEFAULT_BACKOFF_S,
        sleep: Callable[[float], None] = time.sleep,
        concurrency: int = 1,
        progress: Callable[[ProgressEvent], None] | None = None,
        qa: SimilarityQA | None = None,
    ) -> None:
        self.backend, self.voice, self.params, self.cache = backend, voice, params, cache
        self.retries, self.backoff_s, self.sleep = retries, backoff_s, sleep
        self.concurrency = max(1, concurrency)
        self.progress, self.qa = progress, qa
        self._done = 0
        self._total = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # -- public ---------------------------------------------------------------------------

    def run(self, units: list[SynthUnit]) -> list[RenderedUnit]:
        """Render all units in order. Raises SynthesisError naming the failed chunk."""
        self._done, self._total = 0, len(units)
        self._stop.clear()
        results: dict[int, RenderedUnit] = {}
        start = 0
        if self.qa is not None and self.qa.needs_reference and units:
            results[0] = self._render(units[0])  # reference unit first: deterministic reference
            start = 1
        failures = self._render_rest(units, start, results)
        if failures:
            first = failures[0]
            raise SynthesisError(
                f"Synthesis failed for chunk {first[0]}: {first[1]}",
                hint="Completed chunks are cached; re-run to resume.",
            ) from first[1]
        return [results[i] for i in range(len(units))]

    # -- scheduling -----------------------------------------------------------------------

    def _render_rest(
        self, units: list[SynthUnit], start: int, results: dict[int, RenderedUnit]
    ) -> list[tuple[str, Exception]]:
        failures: list[tuple[str, Exception]] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures: list[tuple[int, Future[RenderedUnit]]] = [
                (i, pool.submit(self._guarded, units[i])) for i in range(start, len(units))
            ]
            try:
                for i, fut in futures:
                    self._collect(i, units[i], fut, results, failures)
            except BaseException:
                self._stop.set()
                raise
        return failures

    def _collect(
        self,
        i: int,
        unit: SynthUnit,
        fut: "Future[RenderedUnit]",
        results: dict[int, RenderedUnit],
        failures: list[tuple[str, Exception]],
    ) -> None:
        try:
            results[i] = fut.result()
        except _NO_RETRY:
            raise
        except _SkippedError:
            return
        except Exception as e:
            self._stop.set()
            failures.append((unit.chunk_id, e))

    def _guarded(self, unit: SynthUnit) -> RenderedUnit:
        if self._stop.is_set():
            raise _SkippedError
        return self._render(unit)

    # -- one unit -------------------------------------------------------------------------

    def _render(self, unit: SynthUnit) -> RenderedUnit:
        rendered = self._render_with_qa(unit) if self.qa else self._render_plain(unit)
        with self._lock:
            self._done += 1
            done = self._done
        if self.progress:
            self.progress(
                ProgressEvent(
                    stage="synth",
                    done=done,
                    total=self._total,
                    chunk_id=unit.chunk_id,
                    cached=rendered.cached,
                )
            )
        return rendered

    def _seed(self, take: int) -> int:
        return (self.params.seed or 0) + take

    def _take_key(self, unit: SynthUnit, take: int) -> str:
        """Take 0 is the planner's key; later takes recompute it with the new seed."""
        if take == 0:
            return unit.key
        v = self.voice
        return chunk_key(
            unit.text,
            self.backend.id,
            self.backend.model,
            v.id,
            v.clip_hash,
            self.params.rate,
            self._seed(take),
        )

    def _kind(self, take: int) -> str:
        return "chunks" if take == 0 else "takes"

    def _load_or_synth(self, unit: SynthUnit, take: int) -> tuple[FloatArray, int, bool]:
        kind, key = self._kind(take), self._take_key(unit, take)
        data = self.cache.get_bytes(kind, key, "wav")
        if data is not None:
            try:
                samples, rate = _decode_wav(data)
                return samples, rate, True
            except (RuntimeError, sf.LibsndfileError):
                pass  # corrupt entry: treat as a miss and overwrite
        params = self.params.model_copy(update={"seed": self._seed(take)})
        audio = self._synth_with_retries(unit, params)
        self.cache.put_bytes(kind, key, "wav", _encode_wav(audio.samples, audio.sample_rate))
        return audio.samples, audio.sample_rate, False

    def _render_plain(self, unit: SynthUnit) -> RenderedUnit:
        samples, rate, cached = self._load_or_synth(unit, 0)
        return RenderedUnit(unit=unit, samples=samples, sample_rate=rate, seed=self._seed(0), cached=cached)

    def _synth_with_retries(self, unit: SynthUnit, params: SynthParams) -> PcmAudio:
        for attempt in range(self.retries + 1):
            try:
                return self.backend.synth(unit.text, self.voice, params)
            except _NO_RETRY:
                raise
            except SynthesisError as e:
                if not getattr(e, "retryable", True) or attempt == self.retries:
                    raise
            except Exception:
                if attempt == self.retries:
                    raise
            delay = self.backoff_s * 2**attempt
            self.sleep(delay * (1 + random.uniform(0, JITTER_FRACTION)))  # noqa: S311
        raise AssertionError("unreachable")  # pragma: no cover

    # -- QA -------------------------------------------------------------------------------

    def _render_with_qa(self, unit: SynthUnit) -> RenderedUnit:
        qa = self.qa
        if qa is None:  # pragma: no cover
            return self._render_plain(unit)
        stored = self._stored_best(unit)
        if stored is not None:
            samples, rate, _ = self._load_or_synth(unit, stored.take)
            return RenderedUnit(
                unit=unit,
                samples=samples,
                sample_rate=rate,
                take=stored.take,
                seed=stored.seed,
                similarity=stored.similarity,
                cached=True,
            )
        best: RenderedUnit | None = None
        for take in range(qa.takes_per_chunk):
            samples, rate, cached = self._load_or_synth(unit, take)
            score = qa.score(samples, rate)
            cand = RenderedUnit(
                unit=unit,
                samples=samples,
                sample_rate=rate,
                take=take,
                seed=self._seed(take),
                similarity=score,
                cached=cached,
            )
            if best is None or score > (best.similarity or 0.0):
                best = cand
            if qa.acceptable(score):
                break
        if best is None:  # pragma: no cover
            raise SynthesisError("No takes rendered")
        self._store_best(unit, best)
        return best

    def _stored_best(self, unit: SynthUnit) -> _Take | None:
        text = self.cache.get_text("takes", unit.key, "json")
        if text is None:
            return None
        try:
            rec = _Take.model_validate(json.loads(text))
        except ValueError:
            return None
        return rec if self.cache.exists(self._kind(rec.take), self._take_key(unit, rec.take), "wav") else None

    def _store_best(self, unit: SynthUnit, best: RenderedUnit) -> None:
        rec = _Take(
            take=best.take,
            seed=best.seed or 0,
            similarity=best.similarity or 0.0,
            key=self._take_key(unit, best.take),
        )
        self.cache.put_text("takes", unit.key, "json", rec.model_dump_json())


class _SkippedError(Exception):
    """Internal: a queued unit was skipped because another unit already failed."""


def rich_progress() -> Callable[[ProgressEvent], None]:
    """Progress callback for the CLI; the only place this module writes to the terminal."""
    progress = Progress(
        TextColumn("synth"), BarColumn(), TextColumn("{task.completed}/{task.total}"), TimeRemainingColumn()
    )
    state: dict[str, TaskID] = {}

    def callback(event: ProgressEvent) -> None:
        if "task" not in state:
            progress.start()
            state["task"] = progress.add_task(event.stage, total=event.total)
        progress.update(state["task"], completed=event.done, total=event.total)
        if event.done >= event.total:
            progress.stop()
            state.clear()

    return callback
