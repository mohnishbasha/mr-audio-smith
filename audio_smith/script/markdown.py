"""Script Markdown parse and serialize (ARCHITECTURE 5.2). Round-trips exactly for valid scripts."""

import re

import yaml
from pydantic import BaseModel, ConfigDict, Field

from audio_smith.errors import ScriptInvalidError

SCRIPT_SCHEMA = "audio-smith/script@1"
CHUNK_HEADING = re.compile(r"^## (\d{3,})( \{verbatim\})?\s*$")
FRONTMATTER_KEYS = ("schema", "source", "profile", "lang", "content_hash", "generated_by")


class ScriptMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=SCRIPT_SCHEMA, alias="schema")
    source: str
    profile: str
    lang: str = "en"
    content_hash: str
    generated_by: str


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    text: str
    verbatim: bool = False

    @property
    def id(self) -> str:
        return f"{self.number:03d}"


class Script(BaseModel):
    meta: ScriptMeta
    chunks: list[Chunk]

    def chunk(self, chunk_id: str) -> Chunk:
        return next(c for c in self.chunks if c.id == chunk_id.zfill(3))


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ScriptInvalidError(
            "Script must start with a --- frontmatter block", hint="See ARCHITECTURE 5.2."
        )
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as e:
        raise ScriptInvalidError("Frontmatter block is not closed with ---") from e
    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as e:
        raise ScriptInvalidError(f"Frontmatter is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ScriptInvalidError("Frontmatter must be a mapping")
    return {str(k): v for k, v in data.items()}, "\n".join(lines[end + 1 :])


def parse_chunks(body: str) -> list[Chunk]:
    """Parse the chunk body. Text before the first heading is an error (it would be dropped)."""
    parts: list[tuple[int, bool, list[str]]] = []
    for raw in body.splitlines():
        m = CHUNK_HEADING.match(raw.strip())
        if m:
            parts.append((int(m.group(1)), bool(m.group(2)), []))
        elif parts:
            parts[-1][2].append(raw.rstrip())
        elif raw.strip():
            raise ScriptInvalidError(f"Text before the first chunk heading: {raw.strip()[:60]!r}")
    return [
        Chunk(number=n, verbatim=v, text=re.sub(r"\n{2,}", "\n", "\n".join(lines).strip()))
        for n, v, lines in parts
    ]


def parse_script(text: str) -> Script:
    data, body = _split_frontmatter(text)
    unknown = sorted(set(data) - set(FRONTMATTER_KEYS))
    if unknown:
        raise ScriptInvalidError(f"Unknown frontmatter keys: {', '.join(unknown)}")
    try:
        meta = ScriptMeta.model_validate({k: str(v) for k, v in data.items()})
    except ValueError as e:
        raise ScriptInvalidError(f"Invalid frontmatter: {e}") from e
    if meta.schema_id != SCRIPT_SCHEMA:
        raise ScriptInvalidError(
            f"Unsupported script schema {meta.schema_id!r}", hint=f"Expected {SCRIPT_SCHEMA}."
        )
    return Script(meta=meta, chunks=parse_chunks(body))


def serialize(script: Script) -> str:
    m = script.meta
    head = [
        "---",
        f"schema: {m.schema_id}",
        f"source: {m.source}",
        f"profile: {m.profile}",
        f"lang: {m.lang}",
        f"content_hash: {m.content_hash}",
        f"generated_by: {m.generated_by}",
        "---",
        "",
    ]
    body: list[str] = []
    for c in script.chunks:
        body += [f"## {c.id}{' {verbatim}' if c.verbatim else ''}", c.text, ""]
    return "\n".join(head + body)
