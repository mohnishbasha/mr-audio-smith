"""Block model, text normalization, and content hashing (FR-002, FR-003).

Stored block text keeps the author's punctuation (smart quotes included) but never emoji or
runs of whitespace. Hashing additionally folds smart quotes so a typographic edit does not
force a re-render.
"""

import hashlib
import json
import re
import unicodedata
from typing import Literal

import emoji
from pydantic import BaseModel, ConfigDict, Field

BLOCKS_SCHEMA = "audio-smith/blocks@1"
HASH_FORMAT_VERSION = "h1"
BlockType = Literal["title", "heading", "paragraph", "list_item", "quote", "signature"]
Track = Literal["main", "parent"]

_WS = re.compile(r"\s+")
# Regional indicators (flags), variation selectors, zero-width joiner, keycap combiner, tags.
_EXTRA_EMOJI = re.compile("[\U0001f1e6-\U0001f1ff︎️‍⃣\U000e0020-\U000e007f]")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_SMART = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "′": "'", " ": " "})


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: BlockType
    text: str
    track: Track = "main"
    index: int | None = None
    heading: str | None = None
    verbatim: bool = False


class BlockDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=BLOCKS_SCHEMA, alias="schema")
    source: str
    title: str
    lang: str = "en"
    author: str | None = None
    site_name: str | None = None
    date: str | None = None
    image: str | None = None
    blocks: list[Block]
    warnings: list[str] = Field(default_factory=list)

    def track_blocks(self, track: Track) -> list[Block]:
        return [b for b in self.blocks if b.track == track]

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2, exclude_none=True) + "\n"


def strip_emoji(text: str) -> str:
    return _EXTRA_EMOJI.sub("", emoji.replace_emoji(text, replace=""))


def normalize_text(text: str) -> str:
    """Text as stored: NFC, emoji removed, whitespace collapsed, no space before punctuation."""
    t = unicodedata.normalize("NFC", text).replace(" ", " ")
    t = _WS.sub(" ", strip_emoji(t)).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", t)


def hash_text(text: str) -> str:
    """Text as hashed: stored normalization plus smart quotes folded to straight quotes."""
    return normalize_text(text).translate(_SMART)


def blocks_digest(doc: BlockDoc) -> str:
    """Hash of the narratable content only; markup, whitespace, and ids do not matter."""
    canon = [
        [b.type, b.track, hash_text(b.text), b.heading and hash_text(b.heading), b.verbatim]
        for b in doc.blocks
    ]
    payload = json.dumps(canon, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def content_hash(
    doc: BlockDoc, *, profile_id: str, profile_version: str, backend: str, voice: str, lang: str
) -> str:
    """FR-003: SHA-256 over normalized blocks plus every input that changes the narration."""
    parts = [HASH_FORMAT_VERSION, blocks_digest(doc), profile_id, profile_version, backend, voice, lang]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
