"""Packaging invariants: compose files, Helm values, Dockerfiles, and version alignment."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
CHART = ROOT / "charts" / "mr-audio-smith"


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def prod() -> dict[str, Any]:
    return _load(DEPLOY / "docker-compose.prod.yml")


@pytest.fixture(scope="module")
def local() -> dict[str, Any]:
    return _load(DEPLOY / "docker-compose.local.yml")


def test_compose_prod_no_published_ports_for_internal_services(prod: dict[str, Any]) -> None:
    services = prod["services"]
    for name in ("maya2", "ollama", "audio-smith"):
        assert "ports" not in services[name], f"{name} must not publish ports"
    assert services["caddy"]["ports"], "the reverse proxy is the only published service"


def test_compose_prod_internal_network_and_read_only(prod: dict[str, Any]) -> None:
    assert prod["networks"]["backend"]["internal"] is True
    for name in ("maya2", "ollama", "audio-smith", "caddy"):
        svc = prod["services"][name]
        assert svc["read_only"] is True, name
        assert "/tmp" in svc["tmpfs"][0], name
        assert svc["restart"] == "unless-stopped"
        assert svc["logging"]["options"]["max-size"]
    for name in ("maya2", "ollama"):
        assert prod["services"][name]["networks"] == ["backend"]
    for name in ("maya2", "ollama", "audio-smith", "caddy"):
        assert "memory" in prod["services"][name]["deploy"]["resources"]["limits"]


def test_compose_prod_images_pinned_by_digest(prod: dict[str, Any]) -> None:
    for name, svc in prod["services"].items():
        assert "@sha256:" in svc["image"], f"{name} image must be digest pinned"


def test_compose_prod_requires_token(prod: dict[str, Any]) -> None:
    token = prod["services"]["audio-smith"]["environment"]["AUDIO_SMITH_SERVER_TOKEN"]
    assert token.startswith("${AUDIO_SMITH_SERVER_TOKEN:?")


def test_compose_local_requires_token_and_localhost_only(local: dict[str, Any]) -> None:
    for name in ("audio-smith", "audio-smith-cpu"):
        svc = local["services"][name]
        assert svc["environment"]["AUDIO_SMITH_SERVER_TOKEN"].startswith("${AUDIO_SMITH_SERVER_TOKEN:?")
        assert all(p.startswith("127.0.0.1:") for p in svc["ports"])
    assert "ports" not in local["services"]["maya2"]
    assert "ports" not in local["services"]["ollama"]


def test_compose_maya2_uses_port_8080(local: dict[str, Any], prod: dict[str, Any]) -> None:
    assert local["services"]["audio-smith"]["environment"]["AUDIO_SMITH_MAYA2_URL"] == "http://maya2:8080/v1"
    assert prod["services"]["audio-smith"]["environment"]["AUDIO_SMITH_MAYA2_URL"] == "http://maya2:8080/v1"
    for compose in (local, prod):
        health = compose["services"]["maya2"]["healthcheck"]["test"]
        assert "http://localhost:8080/health" in health
        assert "--port 8080" in compose["services"]["maya2"]["command"][-1]


def test_compose_local_cpu_profile_has_no_gpu_or_maya(local: dict[str, Any]) -> None:
    cpu = local["services"]["audio-smith-cpu"]
    assert cpu["profiles"] == ["cpu"]
    assert cpu["environment"]["AUDIO_SMITH_DEFAULT_BACKEND"] == "kokoro"
    assert cpu["build"]["dockerfile"].endswith("Dockerfile.cpu")
    assert "maya2" not in cpu["depends_on"]
    assert "deploy" not in local["services"]["ollama-cpu"]


def test_helm_values_safe_defaults() -> None:
    values = _load(CHART / "values.yaml")
    assert values["podSecurityContext"]["runAsNonRoot"] is True
    assert values["securityContext"]["readOnlyRootFilesystem"] is True
    assert values["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert values["networkPolicy"]["enabled"] is True
    assert values["maya2"]["persistence"]["size"] == "50Gi"
    assert values["ollama"]["persistence"]["size"] == "100Gi"
    assert values["ingress"]["annotations"]["nginx.ingress.kubernetes.io/proxy-read-timeout"] == "600"
    assert values["ingress"]["annotations"]["nginx.ingress.kubernetes.io/proxy-body-size"] == "10m"


def test_helm_maya2_template_uses_port_8080_and_gpu() -> None:
    text = (CHART / "templates" / "maya2-statefulset.yaml").read_text(encoding="utf-8")
    assert "containerPort: 8080" in text
    assert "path: /health" in text
    service = (CHART / "templates" / "maya2-service.yaml").read_text(encoding="utf-8")
    assert "type: ClusterIP" in service
    assert "port: 8080" in service


def test_helm_ci_values_use_mock_backend_without_gpu_services() -> None:
    ci = _load(CHART / "values-ci.yaml")
    assert ci["config"]["defaultBackend"] == "mock"
    assert ci["maya2"]["enabled"] is False
    assert ci["ollama"]["enabled"] is False


def test_helm_k3s_values_use_nvidia_runtime() -> None:
    k3s = _load(CHART / "values-k3s-gpu.yaml")
    assert k3s["maya2"]["runtimeClassName"] == "nvidia"
    assert k3s["networkPolicy"]["enabled"] is True


def test_chart_version_equals_pyproject_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    chart = _load(CHART / "Chart.yaml")
    assert chart["version"] == pyproject["project"]["version"]
    assert chart["appVersion"] == pyproject["project"]["version"]


@pytest.mark.parametrize("name", ["Dockerfile.cpu", "Dockerfile.cuda"])
def test_app_dockerfiles_are_non_root_with_serve_entrypoint(name: str) -> None:
    text = (DEPLOY / "docker" / name).read_text(encoding="utf-8")
    assert "USER 10001:10001" in text
    assert 'ENTRYPOINT ["mr-audio-smith"]' in text
    assert 'CMD ["serve", "--host", "0.0.0.0"]' in text
    assert "EXPOSE 7340" in text
    assert "HEALTHCHECK" in text


def test_maya2_dockerfile_pinned_and_loopback_by_default() -> None:
    text = (DEPLOY / "docker" / "Dockerfile.maya2").read_text(encoding="utf-8")
    assert "79142d835fc745537fc5ab71a007eba8f425c74c" in text
    assert "--host 127.0.0.1 --port 8080" in text
    assert "EXPOSE 8080" in text
    assert "USER ${APP_UID}" in text
