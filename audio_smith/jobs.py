"""Job model, SQLite store, and the single-worker runner behind the REST server (FR-023, ADR-012).

The pipeline is synchronous and GPU bound, so exactly one worker task drains an asyncio queue and
runs each job in a thread executor. Jobs live in `{out_dir}/jobs.db` so history survives restarts.
"""

import asyncio
import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from audio_smith.config import Settings
from audio_smith.errors import PROBLEM_TYPE_BASE, AudioSmithError
from audio_smith.paths import atomic_write
from audio_smith.tts.runner import ProgressEvent

log = logging.getLogger("audio_smith.jobs")

JobStatus = Literal["queued", "running", "done", "failed"]
JobKind = Literal["narrate", "render"]
JOBS_DIR = "jobs"
DB_NAME = "jobs.db"
RESTART_DETAIL = "server restarted"
INPUT_SCRIPT = "input.script.md"
FIRST_STAGE = "script"
LAST_STAGE = "publish"
HTTP_INTERNAL = 500
Overrides = Callable[[], dict[str, Any]]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    progress REAL NOT NULL DEFAULT 0,
    chunk INTEGER,
    chunks_total INTEGER,
    request TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    out_dir TEXT,
    manifest_path TEXT
)
"""
_UPDATABLE = frozenset(
    {"status", "stage", "progress", "chunk", "chunks_total", "error", "out_dir", "manifest_path"}
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Job(BaseModel):
    """One unit of queued work and its observable state."""

    id: str
    kind: JobKind = "narrate"
    status: JobStatus = "queued"
    stage: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    chunk: int | None = None
    chunks_total: int | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str
    out_dir: Path | None = None
    manifest_path: Path | None = None


def problem_for(exc: Exception, instance: str) -> dict[str, Any]:
    """RFC 9457 problem for a failure; unexpected exceptions are generic so nothing leaks."""
    if isinstance(exc, AudioSmithError):
        return {**exc.to_problem(), "code": exc.code, "instance": instance}
    return {
        "type": PROBLEM_TYPE_BASE + "internal_error",
        "title": "internal_error",
        "status": HTTP_INTERNAL,
        "detail": "Unexpected error while running the job",
        "code": "internal_error",
        "stage": "any",
        "hint": "Check the server log.",
        "instance": instance,
    }


def _encode(key: str, value: Any) -> Any:
    if key == "error" and value is not None:
        return json.dumps(value)
    return str(value) if isinstance(value, Path) else value


class JobStore:
    """SQLite persistence (WAL, one table, JSON columns). Safe to share across threads."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> Job:
        data = dict(row)
        data.pop("seq")
        data["request"] = json.loads(data["request"])
        data["error"] = json.loads(data["error"]) if data["error"] else None
        return Job.model_validate(data)

    def create(self, kind: JobKind, request: dict[str, Any]) -> Job:
        now = _now()
        job = Job(id=uuid.uuid4().hex, kind=kind, request=request, created_at=now, updated_at=now)
        with self._lock:
            self._db.execute(
                "INSERT INTO jobs (id, kind, status, request, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (job.id, kind, job.status, json.dumps(request), now, now),
            )
            self._db.commit()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def update(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        columns = [*fields, "updated_at"]
        values = [*(_encode(k, v) for k, v in fields.items()), _now(), job_id]
        sql = f"UPDATE jobs SET {', '.join(f'{c} = ?' for c in columns)} WHERE id = ?"  # noqa: S608 - whitelisted
        with self._lock:
            self._db.execute(sql, values)
            self._db.commit()

    def list_running(self) -> list[Job]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM jobs WHERE status = 'running' ORDER BY seq").fetchall()
        return [self._row(r) for r in rows]

    def recover(self) -> list[Job]:
        """Mark jobs left running as failed; return queued jobs in creation order."""
        with self._lock:
            stuck = [r["id"] for r in self._db.execute("SELECT id FROM jobs WHERE status = 'running'")]
        for job_id in stuck:
            err = AudioSmithError(RESTART_DETAIL, hint="Submit the job again.")
            self.update(job_id, status="failed", error=problem_for(err, f"/v1/jobs/{job_id}"))
        with self._lock:
            rows = self._db.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY seq").fetchall()
        return [self._row(r) for r in rows]


class JobRunner:
    """One worker task, one job at a time, in submission order.

    Args:
        store: Where jobs persist.
        settings: Pipeline settings; artifacts go under `{out_dir}/jobs/{id}/`.
        overrides: Optional factory of extra keyword arguments (provider, tts, fetcher) for tests.
    """

    def __init__(self, store: JobStore, settings: Settings, *, overrides: Overrides | None = None) -> None:
        self.store = store
        self.settings = settings
        self._overrides = overrides
        self._queue: asyncio.Queue[str] | None = None
        self._task: asyncio.Task[None] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-smith-job")

    @property
    def jobs_root(self) -> Path:
        return self.settings.resolved(self.settings.out_dir) / JOBS_DIR

    async def start(self) -> None:
        """Recover persisted jobs, re-queue the waiting ones, and start the worker."""
        self._queue = asyncio.Queue()
        for job in self.store.recover():
            self._queue.put_nowait(job.id)
        self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._executor.shutdown(wait=True, cancel_futures=True)

    def submit(self, kind: JobKind, request: dict[str, Any]) -> Job:
        """Persist and enqueue; start() must have run."""
        if self._queue is None:
            raise RuntimeError("JobRunner.start() has not run")
        job = self.store.create(kind, request)
        self._queue.put_nowait(job.id)
        return job

    async def _worker(self) -> None:
        if self._queue is None:
            return
        loop = asyncio.get_running_loop()
        while True:
            job_id = await self._queue.get()
            await loop.run_in_executor(self._executor, self._execute, job_id)

    def _progress(self, job_id: str) -> Callable[[ProgressEvent], None]:
        def report(event: ProgressEvent) -> None:
            fraction = event.done / event.total if event.total else 0.0
            self.store.update(
                job_id,
                stage=event.stage,
                progress=round(min(fraction, 1.0), 4),
                chunk=event.done,
                chunks_total=event.total,
            )

        return report

    def _execute(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or job.status != "queued":
            return
        self.store.update(job_id, status="running", stage=FIRST_STAGE, progress=0.0)
        try:
            out_dir, manifest = self._run(job)
        except Exception as e:  # any failure becomes the job's problem document
            if not isinstance(e, AudioSmithError):
                log.exception("job %s crashed", job_id)
            self.store.update(job_id, status="failed", error=problem_for(e, f"/v1/jobs/{job_id}"))
            return
        self.store.update(
            job_id, status="done", stage=LAST_STAGE, progress=1.0, out_dir=out_dir, manifest_path=manifest
        )

    def _run(self, job: Job) -> tuple[Path, Path | None]:
        from audio_smith import api  # noqa: PLC0415 - api re-exports this module

        extra = self._overrides() if self._overrides else {}
        render_extra = {k: v for k, v in extra.items() if k == "tts"}
        job_dir = self.jobs_root / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        req, progress = job.request, self._progress(job.id)
        if job.kind == "render":
            script = atomic_write(job_dir / INPUT_SCRIPT, req["script_markdown"])
            rendered = api.render_script(
                script,
                chunks=req.get("chunks") or None,
                voice=req.get("voice"),
                backend=req.get("backend"),
                out=job_dir,
                settings=self.settings,
                progress=progress,
                **render_extra,
            )
            return rendered.out_dir, None
        opts = req.get("options") or {}
        done = api.narrate(
            req["source"],
            profile=req.get("profile"),
            voice=req.get("voice"),
            backend=req.get("backend"),
            langs=req.get("langs"),
            llm=opts.get("llm"),
            force=bool(opts.get("force")),
            out=job_dir,
            settings=self.settings,
            progress=progress,
            **extra,
        )
        return done.out_dir, done.manifest_path
