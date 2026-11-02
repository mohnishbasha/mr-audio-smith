"""Doctor integration: one non-required row per TTS backend plus a GPU row."""

import importlib.util

from audio_smith.config import Settings
from audio_smith.doctor import Check, CheckResult
from audio_smith.preflight import has_errors
from audio_smith.tts.registry import BACKEND_IDS, get_backend

SKIPPED_IDS = frozenset({"mock"})
EXTRA_HINTS = {
    "kokoro": "Install the extra: uv sync --extra kokoro",
    "chatterbox": "Install the extra: uv sync --extra chatterbox",
    "maya2": "Install the extra: uv sync --extra maya2",
}


def _backend_check(backend_id: str, settings: Settings) -> CheckResult:
    required = backend_id == settings.default_backend
    name = f"tts:{backend_id}"
    try:
        backend = get_backend(backend_id, settings)
        issues = backend.preflight()
    except ImportError as e:
        hint = EXTRA_HINTS.get(backend_id, "Install the missing dependency.")
        return CheckResult(name=name, ok=False, required=required, detail=f"not installed: {e}", hint=hint)
    if has_errors(issues):
        first = next(i for i in issues if i.severity == "error")
        return CheckResult(name=name, ok=False, required=required, detail=first.message, hint=first.hint)
    notes = "; ".join(i.message for i in issues)
    return CheckResult(name=name, ok=True, required=required, detail=notes or "ready")


def backend_checks(settings: Settings) -> list[Check]:
    """Build one Check per real backend; only the default backend's row can fail the doctor."""
    return [
        Check(name=f"tts:{bid}", run=lambda s, b=bid: _backend_check(b, s))
        for bid in BACKEND_IDS
        if bid not in SKIPPED_IDS
    ]


def gpu_check(_: Settings) -> CheckResult:
    """Report CUDA availability; informational because HTTP backends need no local GPU."""
    if importlib.util.find_spec("torch") is None:
        return CheckResult(name="gpu", ok=False, required=False, detail="torch not installed")
    import torch  # noqa: PLC0415

    available = bool(torch.cuda.is_available())
    return CheckResult(
        name="gpu",
        ok=available,
        required=False,
        detail="CUDA available" if available else "CUDA not available",
        hint=None
        if available
        else "Maya 2 in-process mode needs an NVIDIA GPU; use the HTTP server instead.",
    )
