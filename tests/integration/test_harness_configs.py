"""Harness smoke tests (S8-T05): launch the exact command each harness config declares and list tools.

The harness binaries themselves (Goose, OpenCode, Claude Code, Pi) are not installed in CI, so these
tests replay what each harness does at startup: spawn the configured stdio command and run the MCP
handshake plus tools/list. The manual in-harness checks are recorded in docs/TEST_PLAN.md.
"""

import asyncio
import json
import os
import shutil
import tomllib
from pathlib import Path

import pytest
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "mr_audio_smith_narrate",
    "mr_audio_smith_script",
    "mr_audio_smith_render",
    "mr_audio_smith_list_voices",
    "mr_audio_smith_list_profiles",
    "mr_audio_smith_list_backends",
    "mr_audio_smith_status",
    "mr_audio_smith_recommend",
}
pytestmark = pytest.mark.integration


def _resolve(cmd: str, args: list[str]) -> tuple[str, list[str]]:
    """Use the installed console script when present, else `uv run` it from the repo."""
    if shutil.which(cmd):
        return cmd, args
    return "uv", ["run", "--project", str(ROOT), cmd, *args]


async def _tools(cmd: str, args: list[str], tmp_path: Path) -> set[str]:
    command, full = _resolve(cmd, args)
    env = {**os.environ, "AUDIO_SMITH_DEFAULT_BACKEND": "mock", "AUDIO_SMITH_CACHE_DIR": str(tmp_path / "c")}
    params = StdioServerParameters(command=command, args=full, env=env, cwd=str(ROOT))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        return {t.name for t in listed.tools}


def it_harness_goose_toolkit_lists_tools(tmp_path: Path) -> None:
    ext = yaml.safe_load((ROOT / "integrations/goose/toolkit.yaml").read_text(encoding="utf-8"))
    entry = ext["extensions"]["mr-audio-smith"]
    assert entry["type"] == "stdio"
    assert asyncio.run(_tools(entry["cmd"], entry["args"], tmp_path)) == EXPECTED


def it_harness_opencode_config_lists_tools(tmp_path: Path) -> None:
    cfg = json.loads((ROOT / "integrations/opencode/opencode.json.example").read_text(encoding="utf-8"))
    command = cfg["mcp"]["mr-audio-smith"]["command"]
    assert asyncio.run(_tools(command[0], command[1:], tmp_path)) == EXPECTED


def it_harness_claude_code_mcp_add_command_lists_tools(tmp_path: Path) -> None:
    readme = (ROOT / "integrations/claude-code/README.md").read_text(encoding="utf-8")
    line = next(ln.strip() for ln in readme.splitlines() if ln.strip().startswith("claude mcp add"))
    cmd = line.split(" -- ", 1)[1].split()
    assert asyncio.run(_tools(cmd[0], cmd[1:], tmp_path)) == EXPECTED


def test_harness_claude_code_skill_frontmatter_valid() -> None:
    text = (ROOT / "integrations/claude-code/skill/SKILL.md").read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front)
    assert meta["name"] == "narrate-page" and "narrate" in meta["description"].lower()
    assert "consent" in body.lower()


def test_harness_agent_skills_have_frontmatter_and_runner() -> None:
    for skill in (ROOT / ".agent/skills").iterdir():
        meta = yaml.safe_load((skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1])
        assert meta["name"] == skill.name
        assert os.access(skill / "run.sh", os.X_OK)


def test_harness_pyproject_mcp_extra_present() -> None:
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]
    assert any(dep.startswith("mcp") for dep in extras["mcp"])
