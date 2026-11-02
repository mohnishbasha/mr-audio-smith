from importlib.metadata import version

from typer.testing import CliRunner

import audio_smith
from audio_smith.cli import app


def test_init_version_matches_package_metadata() -> None:
    assert audio_smith.__version__ == version("mr-audio-smith")


def test_cli_version_prints_pyproject_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert audio_smith.__version__ in result.output
