"""Docs checks: the generated CLI reference is current and covers every command and flag."""

import importlib.util
from pathlib import Path
from typing import Any

import typer.main

from audio_smith.cli import app

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gen_cli_docs", ROOT / "scripts" / "gen-cli-docs.py")
assert spec and spec.loader
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

CLI_MD = ROOT / "docs" / "reference" / "cli.md"


def test_docs_cli_reference_is_current() -> None:
    assert CLI_MD.read_text(encoding="utf-8") == gen.render(), (
        "docs/reference/cli.md is stale; run: uv run python scripts/gen-cli-docs.py"
    )


def test_docs_every_command_documented() -> None:
    root: Any = typer.main.get_command(app)
    text = CLI_MD.read_text(encoding="utf-8")
    for path, cmd in gen.walk(root, [])[1:]:
        assert f"`mr-audio-smith {' '.join(path)}`" in text, f"command missing: {path}"
        for param in cmd.params:
            if param.param_type_name == "option" and "--help" not in param.opts:
                for name in param.opts:
                    assert f"`{name}`" in text, f"option {name} of {path} missing"


def test_docs_every_cli_flag_documented() -> None:
    root: Any = typer.main.get_command(app)
    text = CLI_MD.read_text(encoding="utf-8")
    flags = {
        o for _, c in gen.walk(root, []) for p in c.params if p.param_type_name == "option" for o in p.opts
    }
    flags.discard("--help")
    assert flags
    assert all(f"`{f}`" in text for f in flags)
