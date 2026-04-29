from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_defines_python_runner_without_dolphindb_server() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "ARG EXTRA=research" in dockerfile
    assert 'uv pip install --system -e ".[${EXTRA}]"' in dockerfile
    assert 'ENTRYPOINT ["moneytrees"]' in dockerfile
    assert "dolphindb/dolphindb" not in dockerfile


def test_dockerignore_excludes_runtime_outputs_and_secrets() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for pattern in (
        ".env",
        "data/",
        "artifacts/",
        "cache/",
        "manifest.sqlite",
        "*.parquet",
        "full_project_source.txt",
    ):
        assert pattern in dockerignore


def test_alpha_compose_separates_moneytrees_and_dolphindb_services() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.alpha.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {"moneytrees", "dolphindb"}
    assert "dolphindb/dolphindb" in services["dolphindb"]["image"]
    assert "./data:/data" not in services["dolphindb"]["volumes"]
    assert "./data/ddb/server/data:/data/ddb/server/data" in services["dolphindb"]["volumes"]
    assert (
        "./docker/dolphindb/modules:/data/ddb/server/data/modules:ro"
        in services["dolphindb"]["volumes"]
    )
    assert services["moneytrees"]["build"]["args"]["EXTRA"] == "${MONEYTREES_EXTRA:-research}"
    assert services["moneytrees"]["depends_on"] == ["dolphindb"]
    assert "./data:/app/data" in services["moneytrees"]["volumes"]
    assert "./artifacts:/app/artifacts" in services["moneytrees"]["volumes"]
    assert services["moneytrees"]["entrypoint"] == ["bash"]
    assert "DOLPHINDB_HOST" in services["moneytrees"]["environment"]
