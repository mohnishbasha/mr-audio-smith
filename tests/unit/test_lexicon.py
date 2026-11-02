from pathlib import Path

import pytest

from audio_smith.errors import UsageError
from audio_smith.script import lexicon


def test_lexicon_apply_whole_word_only() -> None:
    lex = {"Aadi": "AH-dee"}
    assert lexicon.apply("Aadi and Aadish, Aadi!", lex) == "AH-dee and Aadish, AH-dee!"


def test_lexicon_apply_case_sensitive() -> None:
    assert lexicon.apply("aadi Aadi", {"Aadi": "AH-dee"}) == "aadi AH-dee"


def test_lexicon_apply_phrase_before_word() -> None:
    assert lexicon.apply(
        "Mission Control in Houston", {"Houston": "HYOO-stun", "Mission Control": "MISH-un"}
    ) == ("MISH-un in HYOO-stun")
    assert lexicon.apply("unchanged", {}) == "unchanged"


def test_lexicon_stored_script_unchanged_after_apply() -> None:
    stored = "My dear Aadi."
    spoken = lexicon.apply(stored, {"Aadi": "AH-dee"})
    assert stored == "My dear Aadi." and spoken == "My dear AH-dee."


def test_lexicon_project_overrides_profile_entry() -> None:
    assert lexicon.merge({"Aadi": "AH-dee"}, {"Aadi": "AAH-dee"})["Aadi"] == "AAH-dee"


def test_lexicon_merge_profile_and_project(tmp_path: Path) -> None:
    f = tmp_path / "lexicon.yaml"
    f.write_text("Houston: HYOO-stun\n")
    merged = lexicon.merge({"Aadi": "AH-dee"}, lexicon.load_project_lexicon(f))
    assert merged == {"Aadi": "AH-dee", "Houston": "HYOO-stun"}
    assert lexicon.load_project_lexicon(tmp_path / "missing.yaml") == {}


def test_lexicon_invalid_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "lexicon.yaml"
    f.write_text("- a list\n")
    with pytest.raises(UsageError):
        lexicon.load_project_lexicon(f)
    f.write_text("a: [unclosed\n")
    with pytest.raises(UsageError):
        lexicon.load_project_lexicon(f)
