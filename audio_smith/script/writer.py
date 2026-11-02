"""Script writer (FR-005): profile-driven prompt, LLM call, validation, one corrective retry."""

import json
import re
from importlib.resources import files

from audio_smith.blocks import Block, BlockDoc, Track
from audio_smith.errors import ScriptInvalidError
from audio_smith.llm.base import LLMProvider
from audio_smith.profiles.schema import Profile
from audio_smith.script.markdown import Script, ScriptMeta, parse_chunks
from audio_smith.script.validate import ValidationReport, sanitize_script, validate, word_count

WORDS_PER_MINUTE = 130
LENGTH_TOLERANCE = 0.20
DEFAULT_MAX_TOKENS = 4096
_FENCE = re.compile(r"^```[a-z]*\s*$", re.M)
_THINK = re.compile(r"<think>.*?</think>", re.S)


def _template() -> tuple[int, str]:
    raw = (files("audio_smith.script") / "prompts" / "writer.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---", 2)
    version = int(front.strip().split(":", 1)[1])
    return version, body.strip()


PROMPT_VERSION, _TEMPLATE = _template()


def target_words(profile: Profile) -> int:
    return round(profile.writing.target_minutes * WORDS_PER_MINUTE * profile.speech.rate)


def _style_rules(profile: Profile) -> str:
    w = profile.writing
    rules = []
    if w.explain_big_words:
        rules.append("- Explain any big word right where it appears, in words this listener knows.")
    if w.spoken_transitions:
        rules.append('- Use spoken signposts between ideas, for example "Idea number two...".')
    if w.interactive_moments:
        rules.append(
            f"- Include exactly {w.interactive_moments} interactive moments"
            " that invite the listener to join in."
        )
    return "\n".join(rules) or "- Plain, warm, clear sentences."


def build_system_prompt(profile: Profile) -> str:
    """Fill the versioned template from profile data only (profiles are data, ADR and Appendix I)."""
    words = target_words(profile)
    a = profile.audience
    desc = profile.description.strip()
    audience = (desc if not desc or desc.endswith(".") else desc + ".") + (f" Age {a.age}." if a.age else "")
    return _TEMPLATE.format(
        audience=audience.strip(),
        target_words=words,
        min_words=round(words * (1 - LENGTH_TOLERANCE)),
        max_words=round(words * (1 + LENGTH_TOLERANCE)),
        max_sentence_words=profile.writing.max_sentence_words,
        style_rules=_style_rules(profile),
        forbidden=", ".join(profile.writing.forbidden) or "nothing in particular",
        max_chunk_chars=profile.speech.max_chunk_chars,
    )


def _block_payload(b: Block) -> dict[str, object]:
    item: dict[str, object] = {"type": b.type, "text": b.text}
    if b.heading:
        item["heading"] = b.heading
    if b.index is not None:
        item["index"] = b.index
    if b.verbatim:
        item["VERBATIM"] = True
    return item


def build_user_prompt(doc: BlockDoc, track: Track) -> str:
    """Untrusted content goes inside explicit delimiters as JSON (Security Guidelines)."""
    blocks = [_block_payload(b) for b in doc.track_blocks(track)]
    content = json.dumps({"title": doc.title, "blocks": blocks}, ensure_ascii=False, indent=1)
    return f"Write the listening script for this page.\n<<<CONTENT\n{content}\nCONTENT>>>"


def verbatim_sources(doc: BlockDoc, track: Track, profile: Profile) -> list[str]:
    keep_sig = profile.writing.keep_signature_verbatim
    return [b.text for b in doc.track_blocks(track) if b.verbatim and (b.type != "signature" or keep_sig)]


def parse_llm_output(raw: str) -> str:
    """Strip reasoning blocks and code fences; return the chunk body text."""
    return _FENCE.sub("", _THINK.sub("", raw)).strip()


def _length_violation(script: Script, profile: Profile) -> str | None:
    target = target_words(profile)
    words = word_count(script)
    if abs(words - target) > target * LENGTH_TOLERANCE:
        return f"script has {words} words; target is {target} (plus or minus 20 percent)"
    return None


def _attempt(
    provider: LLMProvider,
    system: str,
    user: str,
    meta: ScriptMeta,
    profile: Profile,
    sources: list[str],
    seed: int,
) -> tuple[Script, ValidationReport]:
    raw = provider.complete(system, user, temperature=0.0, seed=seed, max_tokens=DEFAULT_MAX_TOKENS)
    try:
        chunks = parse_chunks(parse_llm_output(raw))
    except ScriptInvalidError as e:
        return Script(meta=meta, chunks=[]), ValidationReport(errors=[e.message])
    script = sanitize_script(Script(meta=meta, chunks=chunks))
    report = validate(script, max_chunk_chars=profile.speech.max_chunk_chars, verbatim_sources=sources)
    length = _length_violation(script, profile)
    if length:
        report.warnings.append(length)
    return script, report


def write_script(
    doc: BlockDoc,
    profile: Profile,
    provider: LLMProvider,
    meta: ScriptMeta,
    *,
    track: Track = "main",
    seed: int = 0,
) -> tuple[Script, list[str]]:
    """Generate and validate a script; on failure retry once with the violations appended.

    Returns the script and its warnings. Raises ScriptInvalidError after the single retry.
    """
    system = build_system_prompt(profile)
    user = build_user_prompt(doc, track)
    sources = verbatim_sources(doc, track, profile)
    script, report = _attempt(provider, system, user, meta, profile, sources, seed)
    length = next((w for w in report.warnings if w.startswith("script has")), None)
    if report.ok and length is None:
        return script, report.warnings
    fixes = report.errors + ([length] if length else [])
    retry_user = (
        user + "\n\nYour previous script had these problems. Fix all of them:\n- " + "\n- ".join(fixes)
    )
    script, report = _attempt(provider, system, retry_user, meta, profile, sources, seed)
    if not report.ok:
        raise ScriptInvalidError(
            "Script failed validation after one corrective retry",
            hint="Edit the script by hand or try another model.",
            violations=report.errors,
        )
    return script, report.warnings
