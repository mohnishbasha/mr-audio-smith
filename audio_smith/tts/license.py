"""License guard (S2-T07): non-commercial weights are opt-in and recorded as manifest warnings."""

from audio_smith.errors import UsageError
from audio_smith.tts.base import Capabilities


def check_license(backend_id: str, caps: Capabilities, accept_noncommercial: bool) -> list[str]:
    """Return manifest warnings; raise when non-commercial weights were not explicitly accepted."""
    if caps.commercial_ok:
        return []
    if not accept_noncommercial:
        raise UsageError(
            f"Backend {backend_id} uses non-commercial weights ({caps.license})",
            hint="Pass --accept-noncommercial (or set AUDIO_SMITH_ACCEPT_NONCOMMERCIAL=true) if allowed.",
        )
    return [f"backend {backend_id} uses non-commercial weights ({caps.license}); accepted by the user"]
