from pathlib import Path

import pytest

from audio_smith.blocks import Block, BlockDoc
from audio_smith.cache.keys import script_key
from audio_smith.errors import ScriptInvalidError
from audio_smith.llm.fake import FakeProvider
from audio_smith.profiles import get_profile
from audio_smith.script.markdown import ScriptMeta
from audio_smith.script.writer import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt,
    parse_llm_output,
    target_words,
    write_script,
)

META = ScriptMeta(source="s", profile="kid-5@1.0.0", lang="en", content_hash="h", generated_by="fake")
SIG = "Your calm spot in every storm, Dad"
DOC = BlockDoc(
    source="s",
    title="T",
    blocks=[
        Block(id="b001", type="title", text="T"),
        Block(id="b002", type="paragraph", text="Hello."),
        Block(id="b003", type="paragraph", text="Grown-up only.", track="parent"),
        Block(id="b004", type="signature", text=SIG, verbatim=True),
    ],
)


def _body(words: int, sig: bool = True) -> str:
    sentences = ["Calm is a quiet spot inside you, and you can find it."] * (words // 12)
    chunks = [
        f"## {i:03d}\n{' '.join(sentences[j : j + 3])}" for i, j in enumerate(range(0, len(sentences), 3), 1)
    ]
    if sig:
        chunks.append(f"## {len(chunks) + 1:03d} {{verbatim}}\n{SIG}")
    return "\n\n".join(chunks)


def test_script_writer_prompt_carries_profile_rules() -> None:
    kid = get_profile("kid-5")
    system = build_system_prompt(kid)
    assert "about 585 spoken words" in system
    assert "at most 360 characters" in system
    assert "at most 12 words" in system
    assert "sarcasm" in system
    assert "## NNN {verbatim}" in system


def test_script_writer_interactive_moments_count_requested() -> None:
    assert "exactly 2 interactive moments" in build_system_prompt(get_profile("kid-5"))
    assert "interactive moments" not in build_system_prompt(get_profile("adult-brief"))


def test_script_writer_user_prompt_wraps_untrusted_content_and_track() -> None:
    user = build_user_prompt(DOC, "main")
    assert user.count("<<<CONTENT") == 1 and user.rstrip().endswith("CONTENT>>>")
    assert '"VERBATIM": true' in user
    assert "Grown-up only." not in user
    assert "Grown-up only." in build_user_prompt(DOC, "parent")


def test_script_writer_target_length_within_20_percent() -> None:
    kid = get_profile("kid-5")
    assert target_words(kid) == round(5 * 130 * 0.9)
    good = FakeProvider(responses=[_body(585)])
    script, warnings = write_script(DOC, kid, good, META)
    assert not any(w.startswith("script has") for w in warnings)
    assert script.chunks[-1].verbatim and script.chunks[-1].text == SIG


def test_script_writer_too_short_retries_then_warns() -> None:
    kid = get_profile("kid-5")
    fake = FakeProvider(responses=[_body(120), _body(120)])
    _, warnings = write_script(DOC, kid, fake, META)
    assert len(fake.calls) == 2
    assert "plus or minus 20 percent" in fake.calls[1][1]
    assert any(w.startswith("script has") for w in warnings)


def test_script_writer_retry_with_violations_succeeds() -> None:
    kid = get_profile("kid-5")
    fake = FakeProvider(responses=[_body(585, sig=False) + "\n\n## 099\n[laugh] Hi.", _body(585)])
    script, _ = write_script(DOC, kid, fake, META)
    assert len(fake.calls) == 2
    assert "[laugh]" in fake.calls[1][1]
    assert script.chunks[-1].text == SIG


def test_script_writer_second_failure_raises() -> None:
    kid = get_profile("kid-5")
    fake = FakeProvider(responses=["no chunk headings here", "## 001\n[whisper] still bad. Yes."])
    with pytest.raises(ScriptInvalidError) as e:
        write_script(DOC, kid, fake, META)
    assert e.value.violations


def test_script_writer_strips_think_blocks_and_fences() -> None:
    assert parse_llm_output("<think>hmm</think>\n```markdown\n## 001\nHi.\n```") == "## 001\nHi."


def test_script_writer_deterministic_temperature_zero_fixed_seed(tmp_path: Path) -> None:
    kid = get_profile("kid-5")
    a = FakeProvider(responses=[_body(585)])
    b = FakeProvider(responses=[_body(585)])
    assert write_script(DOC, kid, a, META) == write_script(DOC, kid, b, META)
    assert a.calls == b.calls


def test_script_writer_prompt_version_in_cache_key() -> None:
    k1 = script_key("h", "kid-5@1.0.0", "ollama/qwen3:14b", "en", PROMPT_VERSION, "main")
    k2 = script_key("h", "kid-5@1.0.0", "ollama/qwen3:14b", "en", PROMPT_VERSION + 1, "main")
    assert k1 != k2


ROOT = Path(__file__).resolve().parents[2]
LETTER_URL = "https://www.aadhish.us/letter-calm-in-the-chaos.html"
GOLDEN_META = ScriptMeta(
    source=LETTER_URL,
    profile="kid-5@1.0.0",
    lang="en",
    content_hash="golden",
    generated_by="ollama/qwen3:14b",
)


def _golden_script() -> str:
    from audio_smith.extract import extract
    from audio_smith.script.markdown import serialize

    doc = extract((ROOT / "tests/fixtures/pages/letter-calm.html").read_text(encoding="utf-8"), LETTER_URL)
    provider = FakeProvider(ROOT / "tests" / "fixtures" / "llm")
    script, _ = write_script(doc, get_profile("kid-5"), provider, GOLDEN_META)
    assert len(provider.calls) == 1, "the recorded response must pass validation without a retry"
    return serialize(script)


def test_script_writer_fake_provider_matches_golden_script() -> None:
    golden = (ROOT / "tests" / "fixtures" / "golden" / "letter-calm.en.script.md").read_text(encoding="utf-8")
    assert _golden_script() == golden
