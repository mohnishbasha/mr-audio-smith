import pytest

from audio_smith import errors


@pytest.mark.parametrize(
    ("cls", "exit_code", "code"),
    [
        (errors.UsageError, 2, "usage"),
        (errors.PreflightError, 3, "preflight_failed"),
        (errors.ExtractError, 4, "extract_failed"),
        (errors.FetchError, 4, "fetch_failed"),
        (errors.ScriptInvalidError, 5, "script_invalid"),
        (errors.SynthesisError, 6, "synthesis_failed"),
        (errors.MasteringError, 7, "mastering_failed"),
        (errors.ConsentError, 8, "consent_missing"),
    ],
)
def test_errors_exit_code_mapping_matches_spec(
    cls: type[errors.AudioSmithError], exit_code: int, code: str
) -> None:
    err = cls("boom", hint="do this")
    assert err.exit_code == exit_code
    assert err.code == code
    assert err.hint == "do this"
    assert str(err) == "boom"


def test_errors_fetch_error_is_extract_error() -> None:
    assert issubclass(errors.FetchError, errors.ExtractError)


def test_errors_problem_json_has_rfc9457_fields() -> None:
    p = errors.ConsentError("no consent", hint="register").to_problem()
    assert p["type"].endswith("consent_missing")
    assert p["title"] == "consent_missing"
    assert p["detail"] == "no consent"
    assert p["hint"] == "register"
    assert p["stage"] == "voice"


def test_errors_synthesis_error_retryable_flag() -> None:
    assert errors.SynthesisError("x").retryable
    assert not errors.SynthesisError("x", retryable=False).retryable
