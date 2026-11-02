"""Doctor integration: report LLM provider health."""

from audio_smith.config import Settings
from audio_smith.doctor import CheckResult
from audio_smith.errors import UsageError
from audio_smith.llm import get_provider
from audio_smith.preflight import has_errors


def llm_check(settings: Settings) -> CheckResult:
    """Required only when the provider has an error-severity issue; warnings stay ok."""
    try:
        provider = get_provider(settings.llm, settings)
    except UsageError as e:
        return CheckResult(name="llm", ok=False, detail=e.message, hint=e.hint)
    issues = provider.preflight()
    if has_errors(issues):
        first = next(i for i in issues if i.severity == "error")
        return CheckResult(name="llm", ok=False, detail=first.message, hint=first.hint)
    notes = "; ".join(i.message for i in issues)
    return CheckResult(name="llm", ok=True, detail=f"{provider.id}" + (f" ({notes})" if notes else ""))
