"""Speaker similarity QA (FR-013, ADR-015): embed each take and compare to a reference voice.

resemblyzer is an optional extra; when absent QA is skipped with a warning, never a crash.
"""

import importlib
import threading
from typing import Any, Protocol

import numpy as np

from audio_smith.tts.base import FloatArray

DEFAULT_THRESHOLD = 0.75
RESEMBLYZER_MISSING_WARNING = (
    "Voice similarity QA skipped: resemblyzer is not installed (pip install 'mr-audio-smith[qa]')."
)


class Embedder(Protocol):
    def embed(self, samples: FloatArray, sample_rate: int) -> np.ndarray[Any, Any]: ...


class ResemblyzerEmbedder:
    """Wraps resemblyzer's VoiceEncoder; imported lazily because it pulls in torch."""

    def __init__(self) -> None:
        module = importlib.import_module("resemblyzer")
        self._encoder = module.VoiceEncoder()
        self._preprocess = module.preprocess_wav

    def embed(self, samples: FloatArray, sample_rate: int) -> np.ndarray[Any, Any]:
        wav = self._preprocess(samples, source_sr=sample_rate)
        return np.asarray(self._encoder.embed_utterance(wav), dtype=np.float32)


def load_embedder() -> Embedder | None:
    """Return a ResemblyzerEmbedder, or None when the qa extra is missing.

    Callers surface RESEMBLYZER_MISSING_WARNING in the manifest when this returns None.
    """
    try:
        return ResemblyzerEmbedder()
    except ImportError:
        return None


def cosine(a: np.ndarray[Any, Any], b: np.ndarray[Any, Any]) -> float:
    """Cosine similarity; 0.0 when either vector has no magnitude."""
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SimilarityQA:
    """Scores takes against a reference embedding computed once.

    Cloned voices pass the reference clip's embedding. Built-in voices have no clip, so the
    reference is the first rendered unit (reference_from_first); the runner renders that
    unit before fanning out so the reference is deterministic under concurrency.
    """

    def __init__(
        self,
        embedder: Embedder,
        reference: np.ndarray[Any, Any] | None,
        threshold: float = DEFAULT_THRESHOLD,
        takes_per_chunk: int = 2,
    ) -> None:
        self.embedder = embedder
        self.reference = reference
        self.threshold = threshold
        self.takes_per_chunk = takes_per_chunk
        self._lock = threading.Lock()

    @classmethod
    def from_reference_clip(
        cls,
        embedder: Embedder,
        samples: FloatArray,
        sample_rate: int,
        threshold: float = DEFAULT_THRESHOLD,
        takes_per_chunk: int = 2,
    ) -> "SimilarityQA":
        return cls(embedder, embedder.embed(samples, sample_rate), threshold, takes_per_chunk)

    @classmethod
    def reference_from_first(
        cls, embedder: Embedder, threshold: float = DEFAULT_THRESHOLD, takes_per_chunk: int = 2
    ) -> "SimilarityQA":
        return cls(embedder, None, threshold, takes_per_chunk)

    @property
    def needs_reference(self) -> bool:
        return self.reference is None

    def score(self, samples: FloatArray, sample_rate: int) -> float:
        """Similarity to the reference; the first sample ever scored becomes it (score 1.0)."""
        emb = self.embedder.embed(samples, sample_rate)
        with self._lock:
            if self.reference is None:
                self.reference = emb
                return 1.0
            return cosine(emb, self.reference)

    def acceptable(self, similarity: float) -> bool:
        return similarity >= self.threshold
