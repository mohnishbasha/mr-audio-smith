import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.slow
def test_packaging_uv_tool_install_runs_version_and_doctor(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv not installed")
    env = {**os.environ, "UV_TOOL_DIR": str(tmp_path / "tools"), "UV_TOOL_BIN_DIR": str(tmp_path / "bin")}
    subprocess.run(["uv", "tool", "install", "--python", "3.12", str(ROOT)], check=True, env=env, timeout=600)
    exe = tmp_path / "bin" / "mr-audio-smith"
    out = subprocess.run([str(exe), "--version"], check=True, capture_output=True, text=True, env=env)
    assert out.stdout.startswith("mr-audio-smith ")
    doc = subprocess.run([str(exe), "doctor", "--json"], capture_output=True, text=True, env=env, check=False)
    assert doc.returncode in (0, 3)
    assert '"results"' in doc.stdout
