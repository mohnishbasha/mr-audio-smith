"""The only module that computes cache keys (Appendix I, principle 6).

Every key starts with the cache format version, so bumping it makes old entries unreachable
instead of misread.
"""

import hashlib

CACHE_FORMAT = "v1"
EXTRACT_VERSION = "1"
_SEP = "\x1f"


def _key(kind: str, *parts: object) -> str:
    payload = _SEP.join([CACHE_FORMAT, kind, *("" if p is None else str(p) for p in parts)])
    return f"{CACHE_FORMAT}-{hashlib.sha256(payload.encode()).hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blocks_key(html: str, parent_headings: tuple[str, ...]) -> str:
    """Extraction output depends only on the page bytes, the extractor version, and routing rules."""
    return _key("blocks", sha256_bytes(html.encode()), EXTRACT_VERSION, "|".join(parent_headings))


def script_key(
    content_hash: str, profile_ref: str, llm: str, lang: str, prompt_version: int, track: str
) -> str:
    return _key("script", content_hash, profile_ref, llm, lang, prompt_version, track)


def chunk_key(
    text: str,
    backend: str,
    model: str,
    voice_id: str,
    voice_clip_hash: str | None,
    rate: float,
    seed: int | None,
) -> str:
    """text is the synthesis text after lexicon substitution (ARCHITECTURE section 7)."""
    return _key("chunk", text, backend, model, voice_id, voice_clip_hash, f"{rate:.3f}", seed)


def track_key(chunk_keys: list[str], mastering: str) -> str:
    return _key("track", *chunk_keys, mastering)
