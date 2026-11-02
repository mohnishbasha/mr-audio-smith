"""Request and response bodies for the REST API (ARCHITECTURE 6.3)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

REF = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,79}$")]
LLM_SPEC = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,119}$")]
LANG = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}$")]
MAX_SOURCE_CHARS = 2048
MAX_SCRIPT_CHARS = 1_000_000
MAX_LANGS = 16
MAX_CHUNKS = 1000
APPROVE_MESSAGE = "approve is not available over HTTP; approval needs Studio"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobOptions(_Strict):
    llm: LLM_SPEC | None = None
    force: bool = False
    approve: bool = False

    @field_validator("approve")
    @classmethod
    def _no_approve(cls, v: bool) -> bool:
        if v:
            raise ValueError(APPROVE_MESSAGE)
        return v


class JobRequest(_Strict):
    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    profile: REF | None = None
    voice: REF | None = None
    backend: REF | None = None
    langs: list[LANG] | None = Field(default=None, max_length=MAX_LANGS)
    options: JobOptions = Field(default_factory=JobOptions)


class ScriptRequest(_Strict):
    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    profile: REF | None = None
    lang: LANG = "en"
    llm: LLM_SPEC | None = None


class RenderRequest(_Strict):
    script_markdown: str = Field(min_length=1, max_length=MAX_SCRIPT_CHARS)
    chunks: list[int] | None = Field(default=None, max_length=MAX_CHUNKS)
    voice: REF | None = None
    backend: REF | None = None


class JobCreated(BaseModel):
    job_id: str


class ProgressView(BaseModel):
    stage_pct: float
    chunk: int | None = None
    chunks_total: int | None = None


class JobView(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    stage: str | None
    progress: ProgressView
    created_at: str
    error: dict[str, Any] | None
