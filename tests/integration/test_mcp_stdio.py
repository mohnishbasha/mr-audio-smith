"""Real stdio session against `mr-audio-smith mcp` (FR-024, TEST_PLAN 5.24)."""

import asyncio
import os
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "tests" / "fixtures" / "pages" / "letter-calm.html"
EXPECTED_TOOLS = {
    "mr_audio_smith_narrate",
    "mr_audio_smith_script",
    "mr_audio_smith_render",
    "mr_audio_smith_list_voices",
    "mr_audio_smith_list_profiles",
    "mr_audio_smith_list_backends",
    "mr_audio_smith_status",
    "mr_audio_smith_recommend",
}
SESSION_TIMEOUT_S = 180

pytestmark = pytest.mark.integration


def _params(tmp_path: Path) -> StdioServerParameters:
    env = {
        **os.environ,
        "AUDIO_SMITH_DEFAULT_BACKEND": "mock",
        "AUDIO_SMITH_LLM": "fake",
        "AUDIO_SMITH_OUT_DIR": str(tmp_path / "out"),
        "AUDIO_SMITH_CACHE_DIR": str(tmp_path / "cache"),
        "AUDIO_SMITH_VOICES_DIR": str(tmp_path / "voices"),
    }
    return StdioServerParameters(
        command="uv", args=["run", "mr-audio-smith", "mcp", "--transport", "stdio"], env=env, cwd=ROOT
    )


async def _session(tmp_path: Path, *, narrate: bool) -> tuple[set[str], dict[str, object]]:
    async with stdio_client(_params(tmp_path)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = {t.name for t in (await session.list_tools()).tools}
        if not narrate:
            return names, {}
        result = await session.call_tool("mr_audio_smith_narrate", {"source": str(PAGE), "backend": "mock"})
        assert not result.is_error, result.content
        return names, dict(result.structured_content or {})


def it_mcp_stdio_transport_list_tools(tmp_path: Path) -> None:
    names, _ = asyncio.run(asyncio.wait_for(_session(tmp_path, narrate=False), SESSION_TIMEOUT_S))
    assert names == EXPECTED_TOOLS


def it_mcp_stdio_narrate_with_mocks(tmp_path: Path) -> None:
    names, data = asyncio.run(asyncio.wait_for(_session(tmp_path, narrate=True), SESSION_TIMEOUT_S))
    assert names == EXPECTED_TOOLS
    manifest = Path(str(data["manifest_path"]))
    assert manifest.is_absolute() and manifest.is_file()
