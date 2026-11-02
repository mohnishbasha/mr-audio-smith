import json
from pathlib import Path

import pytest

from audio_smith.errors import UsageError
from audio_smith.profiles import get_profile, load_all, load_file, parse_profile
from audio_smith.profiles.loader import json_schema

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "profiles"
MINIMAL = "id: p\nversion: 1.0.0\n"


def test_profiles_builtins_kid5_kid8_commute_brief_load() -> None:
    profiles = load_all()
    assert set(profiles) == {"kid-5", "kid-8", "adult-commute", "adult-brief"}
    kid = profiles["kid-5"]
    assert kid.speech.rate == 0.9
    assert kid.lexicon["Aadi"] == "AH-dee"
    assert kid.tracks == {"parent": "adult-brief"}
    assert kid.ref == "kid-5@1.0.0"


def test_profiles_load_invalid_rate_rejected() -> None:
    with pytest.raises(UsageError) as e:
        parse_profile(MINIMAL + "speech:\n  rate: 5\n", "bad.yaml")
    assert "speech.rate" in e.value.message


def test_profiles_load_error_names_field_path() -> None:
    with pytest.raises(UsageError) as e:
        parse_profile(MINIMAL + "writing:\n  target_minuts: 3\n", "typo.yaml")
    assert "writing.target_minuts" in e.value.message
    assert "typo.yaml" in e.value.message


def test_profiles_semantic_version_required() -> None:
    with pytest.raises(UsageError):
        parse_profile("id: p\n", "x")
    with pytest.raises(UsageError):
        parse_profile("id: p\nversion: one\n", "x")


def test_profiles_invalid_yaml_and_non_mapping_rejected() -> None:
    with pytest.raises(UsageError):
        parse_profile("id: [unclosed", "x")
    with pytest.raises(UsageError):
        parse_profile("- a\n- b\n", "x")


def test_profiles_language_code_validated() -> None:
    with pytest.raises(UsageError):
        parse_profile(MINIMAL + "languages: [EN]\n", "x")
    with pytest.raises(UsageError):
        parse_profile(MINIMAL + "lexicon:\n" + "".join(f"  w{i}: x\n" for i in range(501)), "x")


def test_profiles_user_profile_overrides_builtin_same_id(tmp_path: Path) -> None:
    (tmp_path / "kid-5.yaml").write_text("id: kid-5\nversion: 2.0.0\n")
    assert get_profile("kid-5", tmp_path).version == "2.0.0"
    assert get_profile("kid-8", tmp_path).version == "1.0.0"


def test_profiles_custom_commute_fixture_loads() -> None:
    p = load_file(FIX / "custom-commute.yaml")
    assert (p.id, p.writing.target_minutes, p.speech.rate) == ("custom-commute", 8, 1.1)


def test_profiles_get_profile_version_pin_and_unknown() -> None:
    assert get_profile("kid-5@1.0.0").id == "kid-5"
    with pytest.raises(UsageError):
        get_profile("kid-5@9.9.9")
    with pytest.raises(UsageError) as e:
        get_profile("nope")
    assert "kid-5" in (e.value.hint or "")


def test_profiles_track_reference_must_exist(tmp_path: Path) -> None:
    (tmp_path / "x.yaml").write_text("id: x\nversion: 1.0.0\ntracks:\n  parent: missing\n")
    with pytest.raises(UsageError):
        get_profile("x", tmp_path)


def test_profiles_json_schema_matches_pydantic_model() -> None:
    published = json.loads((ROOT / "schemas" / "profile.schema.json").read_text())
    assert published == json.loads(json_schema())
