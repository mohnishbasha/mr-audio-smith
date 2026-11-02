"""Read-only catalog tools: voices, profiles, backends, doctor report, recommendation (FR-024)."""

import importlib.util
import re

from audio_smith import doctor
from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.mcp_server.tools import (
    BackendInfo,
    ProfileInfo,
    RecommendIn,
    RecommendOut,
    StatusCheck,
    StatusOut,
    VoiceInfo,
)
from audio_smith.preflight import has_errors
from audio_smith.profiles.loader import load_all
from audio_smith.tts.registry import BACKEND_IDS, get_backend
from audio_smith.voices import registry as voice_registry

KID_WORDS = re.compile(r"\b(child|children|kid|kids|bedtime|son|daughter|toddler|preschool\w*)\b", re.I)
COMMUTE_WORDS = re.compile(r"\b(commute|commuting|drive|driving|car)\b", re.I)
BRIEF_WORDS = re.compile(r"\b(brief|summary|summarize|tl;?dr|quick)\b", re.I)
AGE_HINT = re.compile(r"\b(?:age[d]?\s*)?(\d{1,2})\s*(?:-?\s*year|yo\b|y/o|yr)|\bage[d]?\s*(\d{1,2})\b", re.I)
YOUNG_MAX_AGE = 6
PROFILE_KID_YOUNG = "kid-5"
PROFILE_KID_OLDER = "kid-8"
CLOUD_LLM_PREFIXES = ("anthropic", "openai_compat")
CLOUD_BACKENDS = frozenset({"openai"})


def list_profiles(settings: Settings) -> list[ProfileInfo]:
    profiles = load_all(settings.profiles_dir)
    return [ProfileInfo(id=p.id, version=p.version, description=p.description) for p in profiles.values()]


def list_backends(settings: Settings) -> list[BackendInfo]:
    """One row per backend; a backend whose extra is missing or whose preflight fails is unavailable."""
    rows: list[BackendInfo] = []
    for bid in BACKEND_IDS:
        try:
            backend = get_backend(bid, settings)
            caps = backend.capabilities()
            available = not has_errors(backend.preflight())
        except Exception:
            rows.append(BackendInfo(id=bid, available=False, languages=[], cloning=False, license="unknown"))
            continue
        rows.append(
            BackendInfo(
                id=bid,
                available=available,
                languages=caps.languages,
                cloning=caps.cloning,
                license=caps.license,
            )
        )
    return rows


def list_voices(settings: Settings) -> list[VoiceInfo]:
    """Registered (cloned, consented) voices first, then built-in voices of installed backends."""
    voices: dict[str, VoiceInfo] = {}
    for rec in voice_registry.list_voices(settings.resolved(settings.voices_dir)):
        voices[rec.id] = VoiceInfo(
            id=rec.id, display_name=rec.display_name, backends=list(rec.backend_hints), cloned=True
        )
    for bid in BACKEND_IDS:
        try:
            builtin = get_backend(bid, settings).capabilities().builtin_voices
        except Exception:  # noqa: S112 - a backend that cannot load simply contributes no voices
            continue
        for vid in builtin:
            known = voices.setdefault(vid, VoiceInfo(id=vid, display_name=vid, backends=[], cloned=False))
            if bid not in known.backends:
                known.backends.append(bid)
    return list(voices.values())


def status(settings: Settings) -> StatusOut:
    """Doctor report: the same checks as `mr-audio-smith doctor`."""
    report = doctor.run_checks(settings, doctor.default_checks())
    checks = [
        StatusCheck(
            name=r.name,
            status="ok" if r.ok else ("fail" if r.required else "warn"),
            detail=r.detail,
            hint=r.hint,
        )
        for r in report.results
    ]
    cloud = settings.llm.startswith(CLOUD_LLM_PREFIXES) or settings.default_backend in CLOUD_BACKENDS
    return StatusOut(ok=report.ok, checks=checks, cloud_providers_active=cloud)


def _age(text: str) -> int | None:
    m = AGE_HINT.search(text)
    return int(next(g for g in m.groups() if g)) if m else None


def _pick_profile(text: str, settings: Settings) -> tuple[str, str]:
    if KID_WORDS.search(text):
        age = _age(text)
        if age is not None and age > YOUNG_MAX_AGE:
            return PROFILE_KID_OLDER, f"child audience, age hint {age}"
        return PROFILE_KID_YOUNG, "child audience" + (f", age hint {age}" if age is not None else "")
    if COMMUTE_WORDS.search(text):
        return "adult-commute", "listening while commuting"
    if BRIEF_WORDS.search(text):
        return "adult-brief", "a short briefing"
    return settings.default_profile, "no audience hints; using the configured default profile"


def _pick_backend(settings: Settings) -> tuple[str, str]:
    try:
        if not has_errors(get_backend("maya2", settings).preflight()):
            return "maya2", "Maya 2 preflight is ok"
    except Exception:  # noqa: S110 - an unloadable backend means it is not the recommendation
        pass
    if importlib.util.find_spec("kokoro") is not None:
        return "kokoro", "Maya 2 is not ready; Kokoro is installed"
    return "mock", "no real TTS backend is ready (placeholder audio only); install an extra or start Maya 2"


def recommend(inp: RecommendIn, settings: Settings) -> RecommendOut:
    """Deterministic keyword rules; never fetches the page."""
    if not (inp.source or inp.description):
        raise UsageError(
            "Give a source or a description", hint="Describe the listener, e.g. 'bedtime for my son'."
        )
    text = f"{inp.description or ''} {inp.source or ''}"
    profile, why_profile = _pick_profile(text, settings)
    backend, why_backend = _pick_backend(settings)
    return RecommendOut(profile=profile, backend=backend, reason=f"{why_profile}; {why_backend}")
