"""Studio HTTP routes (FR-022). A thin layer over audio_smith.api: no pipeline logic lives here.

Security model (BUILD_PROMPT "Server and Studio"): loopback only, a random per-session token on
every /api and /media request, strict CSP, nothing leaves the machine. Errors are problem+json.
"""

import hmac
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from audio_smith import api
from audio_smith.config import Settings
from audio_smith.errors import PROBLEM_TYPE_BASE, AudioSmithError

TOKEN_HEADER = "X-Studio-Token"  # noqa: S105 - a header name, not a secret
PROBLEM_MEDIA_TYPE = "application/problem+json"
PROTECTED_PREFIXES = ("/api", "/media")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; media-src 'self' blob:; connect-src 'self' blob:; img-src 'self' data:; "
        "style-src 'self'; script-src 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
PACKAGE_STATIC = Path(__file__).resolve().parent / "static"
PLACEHOLDER_HTML = (
    "<!doctype html><html lang=en><head><meta charset=utf-8><title>Studio</title></head><body>"
    "<h1>Studio UI not built</h1><p>Run <code>make studio-build</code>, then reload.</p></body></html>"
)
HTTP_FORBIDDEN = 403
TOKEN_HINT = "Open the URL printed by `studio`."  # noqa: S105 - guidance text, not a secret

Next = Callable[[Request], Awaitable[Response]]


class ChunkBody(BaseModel):
    id: str
    text: str
    verbatim: bool = False


class ScriptBody(BaseModel):
    chunks: list[ChunkBody]


class RenderBody(BaseModel):
    seed: int | None = Field(default=None, ge=0)


class SelectBody(BaseModel):
    take: int


class InjectBody(BaseModel):
    path: str
    selector: str | None = None
    dry_run: bool = True


def problem(status: int, code: str, detail: str, hint: str | None = None) -> JSONResponse:
    """RFC 9457 problem document."""
    body = {
        "type": PROBLEM_TYPE_BASE + code,
        "title": code,
        "code": code,
        "status": status,
        "detail": detail,
        "hint": hint,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


def _install_middleware(app: FastAPI, token: str) -> None:
    expected = token.encode()

    @app.middleware("http")
    async def guard(request: Request, call_next: Next) -> Response:
        path = request.url.path
        supplied = request.headers.get(TOKEN_HEADER, "").encode()
        if path.startswith(PROTECTED_PREFIXES) and not hmac.compare_digest(supplied, expected):
            response: Response = problem(
                HTTP_FORBIDDEN,
                "forbidden",
                "Missing or invalid Studio token",
                "Open the URL printed by `studio`.",
            )
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response


def _install_errors(app: FastAPI) -> None:
    @app.exception_handler(AudioSmithError)
    async def audio_smith_error(_: Request, exc: AudioSmithError) -> JSONResponse:
        body = {**exc.to_problem(), "code": exc.code}
        return JSONResponse(body, status_code=exc.http_status, media_type=PROBLEM_MEDIA_TYPE)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        detail = f"{'.'.join(str(p) for p in first.get('loc', ()))}: {first.get('msg', 'invalid request')}"
        return problem(422, "invalid_request", detail)


def _install_api(app: FastAPI, out_dir: Path, settings: Settings, project_root: Path) -> None:
    @app.get("/api/projects")
    def projects() -> list[dict[str, Any]]:
        return [p.model_dump() for p in api.review_list_projects(out_dir)]

    @app.get("/api/projects/{slug}")
    def project(slug: str) -> dict[str, Any]:
        return api.review_load_project(out_dir, slug, settings).model_dump()

    @app.put("/api/projects/{slug}/script")
    def save_script(slug: str, body: ScriptBody) -> dict[str, Any]:
        edits = [api.ReviewChunkEdit(**c.model_dump()) for c in body.chunks]
        return api.review_save_script(out_dir, slug, edits, settings).model_dump()

    @app.post("/api/projects/{slug}/chunks/{chunk_id}/render")
    def render(slug: str, chunk_id: str, body: RenderBody | None = None) -> dict[str, Any]:
        seed = body.seed if body else None
        return api.review_render_take(out_dir, slug, chunk_id, settings, seed=seed).model_dump()

    @app.post("/api/projects/{slug}/chunks/{chunk_id}/select")
    def select(slug: str, chunk_id: str, body: SelectBody) -> dict[str, bool]:
        api.review_select_take(out_dir, slug, chunk_id, body.take)
        return {"ok": True}

    @app.post("/api/projects/{slug}/master")
    def master(slug: str) -> dict[str, Any]:
        return api.review_master_selected(out_dir, slug, settings).model_dump()

    @app.post("/api/projects/{slug}/approve")
    def approve(slug: str) -> dict[str, bool]:
        api.review_approve(out_dir, slug)
        return {"approved": True}

    @app.post("/api/projects/{slug}/inject")
    def inject(slug: str, body: InjectBody) -> dict[str, Any]:
        outcome = api.review_inject_from_studio(
            project_root, out_dir, slug, body.path, body.selector, body.dry_run
        )
        return outcome.model_dump()


def _install_files(app: FastAPI, out_dir: Path, static: Path) -> None:
    @app.get("/media/{slug}/{file:path}")
    def media(slug: str, file: str) -> FileResponse:
        return FileResponse(api.review_media_path(out_dir, slug, file))

    @app.get("/player/audio-smith-player.js")
    def player() -> Response:
        bundle = api.review_player_bundle()
        if bundle is None:
            return problem(404, "not_found", "Player bundle not built", "Run `make player-build`.")
        return FileResponse(bundle, media_type="text/javascript")

    index = static / "index.html"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def home() -> Response:
        return FileResponse(index) if index.is_file() else HTMLResponse(PLACEHOLDER_HTML)


def create_app(
    out_dir: Path,
    settings: Settings,
    token: str,
    *,
    static_dir: Path | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    """Build the Studio app. `token` guards /api and /media; `project_root` bounds page injection."""
    app = FastAPI(title="mr-audio-smith Studio", docs_url=None, redoc_url=None, openapi_url=None)
    root = (project_root or Path.cwd()).resolve()
    _install_middleware(app, token)
    _install_errors(app)
    _install_api(app, out_dir.expanduser().resolve(), settings, root)
    _install_files(app, out_dir.expanduser().resolve(), static_dir or PACKAGE_STATIC)
    return app
