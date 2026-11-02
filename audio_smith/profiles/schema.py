"""Profile YAML schema (ARCHITECTURE 5.3). Profiles are data: no audience logic lives in code."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROFILE_SCHEMA = "audio-smith/profile@1"
SEMVER = r"^\d+\.\d+\.\d+$"
LEXICON_MAX = 500


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Audience(_Strict):
    age: int | None = Field(default=None, ge=3, le=99)
    attention_minutes: float | None = Field(default=None, gt=0)


class Writing(_Strict):
    target_minutes: float = Field(default=5, ge=0.5, le=60)
    max_sentence_words: int = Field(default=20, ge=4, le=60)
    explain_big_words: bool = False
    spoken_transitions: bool = False
    interactive_moments: int = Field(default=0, ge=0, le=10)
    keep_signature_verbatim: bool = True
    forbidden: list[str] = Field(default_factory=list)
    parent_headings: list[str] | None = None


class Speech(_Strict):
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    pause_after_heading_ms: int = Field(default=600, ge=0, le=3000)
    pause_between_chunks_ms: int = Field(default=300, ge=0, le=3000)
    max_chunk_chars: int = Field(default=400, ge=80, le=400)


class Mastering(_Strict):
    intro_sting: str | None = None
    outro_sting: str | None = None
    music_bed: str | None = None


class QA(_Strict):
    takes_per_chunk: int = Field(default=2, ge=1, le=5)
    threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class Profile(_Strict):
    """One listener description. Unknown keys are errors so typos never change behavior silently."""

    schema_id: str = Field(default=PROFILE_SCHEMA, alias="schema", pattern=r"^audio-smith/profile@1$")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    version: str = Field(pattern=SEMVER)
    description: str = Field(default="", max_length=200)
    audience: Audience = Field(default_factory=Audience)
    writing: Writing = Field(default_factory=Writing)
    speech: Speech = Field(default_factory=Speech)
    languages: list[str] = Field(default_factory=lambda: ["en"], min_length=1)
    tracks: dict[Literal["parent"], str] = Field(default_factory=dict)
    mastering: Mastering = Field(default_factory=Mastering)
    lexicon: dict[str, str] = Field(default_factory=dict)
    qa: QA = Field(default_factory=QA)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("languages")
    @classmethod
    def _langs(cls, v: list[str]) -> list[str]:
        for code in v:
            if not code.isalpha() or not 2 <= len(code) <= 3 or code != code.lower():
                raise ValueError(f"language code {code!r} must be 2-3 lowercase letters")
        return v

    @field_validator("lexicon")
    @classmethod
    def _lexicon(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > LEXICON_MAX:
            raise ValueError(f"lexicon has {len(v)} entries; max {LEXICON_MAX}")
        return v

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"
