"""Deterministic enforcement of verbatim blocks (FR-005).

Models paraphrase, drop, or blank out text they were told to copy exactly. Instead of spending
the single corrective retry on that, the exact source text is spliced in by code: a chunk that
nearly matches a verbatim source is replaced in place, empty verbatim chunks are dropped, and
any source still missing is appended (the signature always last).
"""

from difflib import SequenceMatcher

from audio_smith.script.markdown import Chunk
from audio_smith.script.validate import plain_text

NEAR_MATCH_RATIO = 0.6


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, plain_text(a).lower(), plain_text(b).lower()).ratio()


def _best_match(chunks: list[Chunk], source: str, taken: set[int]) -> int | None:
    scored = [(i, _similar(c.text, source)) for i, c in enumerate(chunks) if i not in taken]
    best = max(scored, key=lambda t: t[1], default=None)
    return best[0] if best and best[1] >= NEAR_MATCH_RATIO else None


def enforce_verbatim(chunks: list[Chunk], sources: list[str], signature: str | None) -> list[Chunk]:
    """Return renumbered chunks in which every source appears exactly once as a verbatim chunk."""
    work = [c for c in chunks if plain_text(c.text) or not c.verbatim]
    taken: set[int] = set()
    missing: list[str] = []
    for src in sources:
        idx = _best_match(work, src, taken)
        if idx is None:
            missing.append(src)
            continue
        work[idx] = work[idx].model_copy(update={"text": src, "verbatim": True})
        taken.add(idx)
    if signature is not None:
        sig_idx = next((i for i in taken if work[i].text == signature), None)
        if sig_idx is not None and sig_idx != len(work) - 1:
            work.append(work.pop(sig_idx))
    tail = [s for s in missing if s != signature] + ([signature] if signature in missing else [])
    work += [Chunk(number=0, text=s, verbatim=True) for s in tail]
    return [c.model_copy(update={"number": n}) for n, c in enumerate(work, 1)]
