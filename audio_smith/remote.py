"""Remote mode (S7-T04): submit a narration to a `mr-audio-smith serve` instance and download it.

The GPU box runs the server; a laptop or a CI runner without a GPU calls it. The voice clip and
its consent record live on the server; this client only sends the page URL and options.
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from audio_smith.errors import AudioSmithError, SynthesisError, UsageError
from audio_smith.orchestrate import NarrateResult
from audio_smith.paths import atomic_write, ensure_inside, safe_slug
from audio_smith.publish.inject import inject_file
from audio_smith.publish.manifest import Manifest

POLL_INTERVAL_S = 2.0
DEFAULT_TIMEOUT_S = 1800.0
HTTP_TIMEOUT_S = 60.0
TERMINAL = {"done", "failed"}


class RemoteError(AudioSmithError):
    code = "remote_failed"
    stage = "remote"
    exit_code = 6
    http_status = 502


def _raise_for_problem(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        body: dict[str, Any] = resp.json()
    except ValueError:
        body = {"detail": resp.text[:200]}
    detail = str(body.get("detail") or body.get("title") or resp.reason_phrase)
    if resp.status_code == 401:
        raise UsageError(
            f"Server rejected the token: {detail}", hint="Pass --token or set AUDIO_SMITH_SERVER_TOKEN."
        )
    raise RemoteError(f"Server error {resp.status_code}: {detail}", hint=body.get("hint"))


class RemoteClient:
    """Thin client over the REST contract in docs/ARCHITECTURE.md."""

    def __init__(self, base_url: str, token: str | None, *, client: httpx.Client | None = None) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.base = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=HTTP_TIMEOUT_S)
        self.headers = headers

    def submit(self, payload: dict[str, Any]) -> str:
        resp = self.http.post(f"{self.base}/v1/jobs", json=payload, headers=self.headers)
        _raise_for_problem(resp)
        return str(resp.json()["job_id"])

    def status(self, job_id: str) -> dict[str, Any]:
        resp = self.http.get(f"{self.base}/v1/jobs/{job_id}", headers=self.headers)
        _raise_for_problem(resp)
        data: dict[str, Any] = resp.json()
        return data

    def wait(
        self,
        job_id: str,
        *,
        timeout_s: float,
        sleep: Callable[[float], None] = time.sleep,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while True:
            st = self.status(job_id)
            if on_status:
                on_status(st)
            if st.get("status") in TERMINAL:
                return st
            if time.monotonic() > deadline:
                raise RemoteError(
                    f"Job {job_id} did not finish in {timeout_s:.0f} s", hint="Check the server logs."
                )
            sleep(POLL_INTERVAL_S)

    def manifest(self, job_id: str) -> Manifest:
        resp = self.http.get(f"{self.base}/v1/jobs/{job_id}/manifest", headers=self.headers)
        _raise_for_problem(resp)
        return Manifest.model_validate(resp.json())

    def download(self, job_id: str, name: str, dest: Path) -> Path:
        resp = self.http.get(f"{self.base}/v1/jobs/{job_id}/files/{name}", headers=self.headers)
        _raise_for_problem(resp)
        return atomic_write(dest, resp.content)


def _files(manifest: Manifest, slug: str) -> list[str]:
    names = [f"{slug}.manifest.json", f"{slug}.embed.html"]
    for t in manifest.tracks:
        names += [n for n in (t.file, t.captions, t.opus) if n]
    return names


def narrate_remote(
    source: str,
    *,
    server: str,
    token: str | None,
    out: Path,
    profile: str | None = None,
    voice: str | None = None,
    backend: str | None = None,
    langs: list[str] | None = None,
    llm: str | None = None,
    force: bool = False,
    inject: Path | None = None,
    selector: str = "h1",
    timeout_s: float = DEFAULT_TIMEOUT_S,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> NarrateResult:
    """Run the pipeline on a remote server and mirror its outputs into OUT/<slug>/."""
    if not source.startswith(("http://", "https://")):
        raise UsageError(
            "Remote mode needs a page URL the server can fetch", hint="Publish the page or run locally."
        )
    remote = RemoteClient(server, token, client=client)
    payload: dict[str, Any] = {
        "source": source,
        "profile": profile,
        "voice": voice,
        "backend": backend,
        "langs": langs,
        "options": {"llm": llm, "force": force},
    }
    job_id = remote.submit({k: v for k, v in payload.items() if v is not None})
    final = remote.wait(job_id, timeout_s=timeout_s, sleep=sleep)
    if final.get("status") != "done":
        err = final.get("error") or {}
        raise SynthesisError(
            f"Remote job {job_id} failed: {err.get('detail', 'unknown error')}", hint=err.get("hint")
        )
    manifest = remote.manifest(job_id)
    slug = safe_slug(source)
    out_dir = ensure_inside(out.expanduser(), out.expanduser() / slug)
    for name in _files(manifest, slug):
        remote.download(job_id, name, ensure_inside(out_dir, out_dir / name))
    embed = out_dir / f"{slug}.embed.html"
    changed = False
    if inject is not None:
        changed = inject_file(
            inject, embed.read_text(encoding="utf-8").rstrip("\n"), selector=selector
        ).changed
    return NarrateResult(
        manifest_path=out_dir / f"{slug}.manifest.json",
        manifest=manifest,
        out_dir=out_dir,
        embed_path=embed,
        injected=inject,
        inject_changed=changed,
        warnings=manifest.warnings,
    )
