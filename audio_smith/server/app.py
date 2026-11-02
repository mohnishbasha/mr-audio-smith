"""REST server (FR-023, ADR-012): a thin async layer over audio_smith.api and the job runner.

Security model (BUILD_PROMPT "Server and Studio"): loopback by default, bearer token required on any
other bind and enforced whenever configured, per-token rate limit on job creation, only http(s)
sources, file serving confined to the job directory, problem+json for every error.
"""

import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from audio_smith import api
from audio_smith.config import Settings
from audio_smith.errors import PROBLEM_TYPE_BASE, AudioSmithError, UsageError
from audio_smith.server import auth
from audio_smith.server.models import (
    JobCreated,
    JobRequest,
    JobView,
    ProgressView,
    RenderRequest,
    ScriptRequest,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"
HTTP_UNPROCESSABLE = 422
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".vtt": "text/vtt",
    ".html": "text/html",
    ".json": "application/json",
    ".md": "text/markdown",
    ".js": "text/javascript",
}
FILE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "attachment",
}
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
MAX_FORM_FIELDS = 8
SCRIPT_FIELD = "script"


def problem(
    status: int, code: str, detail: str, hint: str | None = None, instance: str | None = None
) -> JSONResponse:
    """RFC 9457 problem response."""
    body = {
        "type": PROBLEM_TYPE_BASE + code,
        "title": code,
        "code": code,
        "status": status,
        "detail": detail,
        "hint": hint,
        "instance": instance,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


def _install_errors(app: FastAPI) -> None:
    @app.exception_handler(AudioSmithError)
    async def audio_smith_error(request: Request, exc: AudioSmithError) -> JSONResponse:
        body = {**exc.to_problem(), "code": exc.code, "instance": request.url.path}
        headers: dict[str, str] = {}
        if isinstance(exc, auth.UnauthorizedError):
            headers["WWW-Authenticate"] = "Bearer"
        if isinstance(exc, auth.RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(body, exc.http_status, headers, PROBLEM_MEDIA_TYPE)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        detail = f"{where}: {first.get('msg', 'invalid request')}"
        return problem(HTTP_UNPROCESSABLE, "invalid_request", detail, instance=request.url.path)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return problem(exc.status_code, code, str(exc.detail), instance=request.url.path)


def _install_headers(app: FastAPI, origins: list[str]) -> None:
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Any]) -> Response:
        response: Response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


def _require_job(runner: api.JobRunner, job_id: str) -> api.Job:
    job = runner.store.get(job_id) if re.fullmatch(r"[0-9a-f]{32}", job_id) else None
    if job is None:
        raise auth.NotFoundError(f"No such job: {job_id[:40]}", hint="Check the job id.")
    return job


def _view(job: api.Job) -> JobView:
    return JobView(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        progress=ProgressView(stage_pct=job.progress, chunk=job.chunk, chunks_total=job.chunks_total),
        created_at=job.created_at,
        error=job.error,
    )


def _check_source(source: str) -> None:
    if not source.lower().startswith(("http://", "https://")):
        raise auth.InvalidRequestError(
            "source must be an http or https URL", hint="Local paths are not accepted over HTTP."
        )


def _job_file(runner: api.JobRunner, job: api.Job, name: str) -> Path:
    suffix = Path(name).suffix.lower()
    if not FILE_NAME_RE.fullmatch(name) or ".." in name or suffix not in MEDIA_TYPES:
        raise auth.NotFoundError("No such file", hint="Use a name from the manifest.")
    root = (runner.jobs_root / job.id).resolve()
    target = (job.out_dir / name).resolve() if job.out_dir else root / name
    if not target.is_file() or root not in target.parents:
        raise auth.NotFoundError("No such file", hint="Use a name from the manifest.")
    return target


async def _render_body(request: Request) -> RenderRequest:
    """JSON body, or multipart with a `script` file/text field plus optional text fields."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form(max_fields=MAX_FORM_FIELDS)
        raw = form.get(SCRIPT_FIELD)
        text = (
            (await raw.read()).decode("utf-8", "replace") if isinstance(raw, UploadFile) else str(raw or "")
        )
        chunks = str(form.get("chunks") or "")
        data: dict[str, Any] = {"script_markdown": text}
        if chunks:
            data["chunks"] = [c for c in re.split(r"[,\s]+", chunks) if c]
        for key in ("voice", "backend"):
            if form.get(key):
                data[key] = str(form[key])
        try:
            return RenderRequest.model_validate(data)
        except ValidationError as e:
            raise auth.InvalidRequestError(str(e.errors()[0]["msg"])) from e
    try:
        return RenderRequest.model_validate_json(await request.body())
    except ValidationError as e:
        first = e.errors()[0]
        raise auth.InvalidRequestError(f"{'.'.join(map(str, first['loc']))}: {first['msg']}") from e


def _install_jobs(
    router: APIRouter, runner: api.JobRunner, settings: Settings, limiter: auth.SlidingWindowLimiter
) -> None:
    expected = auth.configured_token(settings)

    def throttle(request: Request) -> None:
        key = auth.client_key(
            request.headers.get("authorization"), request.client.host if request.client else None, expected
        )
        limiter.hit(key)

    _install_render(router, runner, settings, throttle)

    @router.post("/jobs", status_code=202)
    async def create_job(body: JobRequest, response: Response, _: None = Depends(throttle)) -> JobCreated:
        _check_source(body.source)
        await run_in_threadpool(api.precheck_voice, body.voice, body.backend, settings)
        job = runner.submit("narrate", body.model_dump(mode="json"))
        response.headers["Location"] = f"/v1/jobs/{job.id}"
        return JobCreated(job_id=job.id)

    @router.get("/jobs/{job_id}")
    async def job_status(job_id: str) -> JobView:
        return _view(_require_job(runner, job_id))

    @router.get("/jobs/{job_id}/manifest")
    async def job_manifest(job_id: str) -> FileResponse:
        job = _require_job(runner, job_id)
        if job.status != "done" or job.manifest_path is None or not job.manifest_path.is_file():
            raise auth.NotFoundError("Manifest not available yet", hint="Poll the job until it is done.")
        return FileResponse(job.manifest_path, media_type="application/json")

    @router.get("/jobs/{job_id}/files/{name}")
    async def job_file(job_id: str, name: str) -> FileResponse:
        path = _job_file(runner, _require_job(runner, job_id), name)
        return FileResponse(path, media_type=MEDIA_TYPES[path.suffix.lower()], headers=FILE_HEADERS)


def _install_render(
    router: APIRouter, runner: api.JobRunner, settings: Settings, throttle: Callable[[Request], None]
) -> None:
    @router.post("/render", status_code=202)
    async def render(request: Request, response: Response, _: None = Depends(throttle)) -> JobCreated:
        body = await _render_body(request)
        await run_in_threadpool(api.check_script_text, body.script_markdown)
        await run_in_threadpool(api.precheck_voice, body.voice, body.backend, settings)
        payload = body.model_dump(mode="json")
        payload["chunks"] = [str(c) for c in body.chunks] if body.chunks else None
        job = runner.submit("render", payload)
        response.headers["Location"] = f"/v1/jobs/{job.id}"
        return JobCreated(job_id=job.id)


def _install_catalog(router: APIRouter, settings: Settings, overrides: Callable[[], dict[str, Any]]) -> None:
    @router.post("/scripts")
    def make_script(body: ScriptRequest) -> dict[str, Any]:
        _check_source(body.source)
        extra = overrides()
        preview = api.script_preview(
            body.source,
            settings,
            profile=body.profile,
            llm=body.llm,
            lang=body.lang,
            fetcher=extra.get("fetcher"),
            provider=extra.get("provider"),
        )
        return preview.model_dump()

    @router.get("/voices")
    def voices() -> list[dict[str, Any]]:
        return [v.model_dump() for v in api.list_voices_summary(settings)]

    @router.get("/profiles")
    def profiles() -> list[dict[str, Any]]:
        return [p.model_dump() for p in api.list_profiles_summary(settings)]

    @router.get("/backends")
    def backends() -> list[dict[str, Any]]:
        return [b.model_dump() for b in api.list_backends_summary(settings)]


def create_app(
    settings: Settings,
    *,
    runner: api.JobRunner | None = None,
    overrides: Callable[[], dict[str, Any]] | None = None,
) -> FastAPI:
    """Build the REST app; raises UsageError on a non-loopback bind without a token.

    Args:
        settings: Server and pipeline settings.
        runner: Optional prebuilt runner (tests); otherwise one is created over `{out_dir}/jobs.db`.
        overrides: Optional factory of pipeline keyword arguments (provider, tts, fetcher) for tests.
    """
    auth.require_safe_bind(settings)
    if settings.server_rate_limit_per_hour < 1:
        raise UsageError("server_rate_limit_per_hour must be at least 1")
    out_dir = settings.resolved(settings.out_dir)
    run = runner or api.JobRunner(api.JobStore(out_dir / "jobs.db"), settings, overrides=overrides)
    expected = auth.configured_token(settings)
    limiter = auth.SlidingWindowLimiter(settings.server_rate_limit_per_hour)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await run.start()
        yield
        await run.stop()
        run.store.close()

    app = FastAPI(title="mr-audio-smith", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.runner = run
    _install_errors(app)
    _install_headers(app, settings.server_cors_origins)

    def authenticate(request: Request) -> None:
        auth.check_bearer(request.headers.get("authorization"), expected)

    router = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])
    _install_jobs(router, run, settings, limiter)
    _install_catalog(router, settings, overrides or dict)
    app.include_router(router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        return {"status": "ready", "checks": api.require_ready(settings).checks}

    return app
