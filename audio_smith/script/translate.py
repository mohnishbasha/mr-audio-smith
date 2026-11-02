"""Translation of a validated script into extra language tracks (FR-008).

Chunk boundaries and pause markers must survive one to one, so audio for every language lines
up chunk for chunk; a misaligned translation gets one corrective retry, then fails.
"""

from importlib.resources import files

from audio_smith.errors import ScriptInvalidError
from audio_smith.llm.base import LLMProvider
from audio_smith.profiles.schema import Profile
from audio_smith.script.markdown import Script, parse_chunks, serialize
from audio_smith.script.validate import PAUSE, sanitize_script, validate
from audio_smith.script.writer import DEFAULT_MAX_TOKENS, parse_llm_output

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "or": "Odia",
    "pa": "Punjabi",
    "as": "Assamese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}


def _template() -> tuple[int, str]:
    raw = (files("audio_smith.script") / "prompts" / "translate.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---", 2)
    return int(front.strip().split(":", 1)[1]), body.strip()


TRANSLATE_PROMPT_VERSION, _TEMPLATE = _template()


def alignment_errors(source: Script, translated: Script) -> list[str]:
    """Chunk count, numbering, verbatim flags, and pause markers must match the source exactly."""
    if len(source.chunks) != len(translated.chunks):
        return [f"expected {len(source.chunks)} chunks, got {len(translated.chunks)}"]
    errors: list[str] = []
    for src, tr in zip(source.chunks, translated.chunks, strict=True):
        if src.number != tr.number or src.verbatim != tr.verbatim:
            errors.append(f"chunk {src.id}: heading changed")
        if PAUSE.findall(src.text) != PAUSE.findall(tr.text):
            errors.append(f"chunk {src.id}: pause markers changed")
    return errors


def _attempt(
    provider: LLMProvider, system: str, user: str, source: Script, lang: str, max_chars: int
) -> tuple[Script, list[str]]:
    raw = provider.complete(system, user, temperature=0.0, seed=0, max_tokens=DEFAULT_MAX_TOKENS)
    meta = source.meta.model_copy(update={"lang": lang})
    try:
        script = sanitize_script(Script(meta=meta, chunks=parse_chunks(parse_llm_output(raw))))
    except ScriptInvalidError as e:
        return Script(meta=meta, chunks=[]), [e.message]
    errors = alignment_errors(source, script) + validate(script, max_chunk_chars=max_chars).errors
    return script, errors


def translate_script(source: Script, lang: str, profile: Profile, provider: LLMProvider) -> Script:
    """Translate with one corrective retry; raise ScriptInvalidError if alignment still fails."""
    system = _TEMPLATE.format(
        language_name=LANGUAGE_NAMES.get(lang, lang),
        lang=lang,
        audience=profile.description,
        chunk_count=len(source.chunks),
    )
    body = serialize(source).split("---", 2)[2].strip()
    user = f"Translate this script.\n<<<SCRIPT\n{body}\nSCRIPT>>>"
    max_chars = profile.speech.max_chunk_chars
    script, errors = _attempt(provider, system, user, source, lang, max_chars)
    if not errors:
        return script
    retry = (
        user + "\n\nYour previous translation had these problems. Fix all of them:\n- " + "\n- ".join(errors)
    )
    script, errors = _attempt(provider, system, retry, source, lang, max_chars)
    if errors:
        raise ScriptInvalidError(
            f"Translation to {lang} is misaligned after one retry",
            violations=errors,
            hint="Try a stronger model or edit the translated script by hand.",
        )
    return script
