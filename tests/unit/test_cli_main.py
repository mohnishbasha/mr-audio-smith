import sys

import pytest

from audio_smith import cli
from audio_smith.errors import ConsentError


def test_cli_main_maps_audio_smith_error_to_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_: object) -> None:
        raise ConsentError("no consent", hint="register the voice")

    monkeypatch.setattr(cli, "app", boom)
    monkeypatch.setattr(sys, "argv", ["mr-audio-smith", "run"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 8


def test_cli_main_unknown_command_is_usage_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["mr-audio-smith", "definitely-not-a-command"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2


def test_cli_main_keyboard_interrupt_exits_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(**_: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "app", interrupt)
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 130
