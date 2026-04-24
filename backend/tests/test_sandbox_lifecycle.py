from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from smrt_agent.sandbox.lifecycle import (
    generate_dockerfile,
    build_image,
    start_container,
    health_check,
    SANDBOX_PORT,
)


def test_generate_dockerfile_creates_file(tmp_path):
    canonical = str(tmp_path)
    generate_dockerfile(canonical)
    df = tmp_path / ".smrt" / "sandbox" / "Dockerfile"
    assert df.exists()
    content = df.read_text()
    assert "FROM python:3.11-slim" in content
    assert "EXPOSE 8080" in content


def test_build_image_calls_docker_build(tmp_path):
    generate_dockerfile(str(tmp_path))
    mock_client = MagicMock()
    mock_image = MagicMock()
    mock_image.id = "sha256:abc123"
    mock_client.images.build.return_value = (mock_image, [])

    tag = build_image(mock_client, str(tmp_path))

    assert mock_client.images.build.called
    build_kwargs = mock_client.images.build.call_args.kwargs
    assert build_kwargs["rm"] is True
    assert tag.startswith("smrt-sandbox-")


def test_start_container_applies_resource_caps(tmp_path):
    generate_dockerfile(str(tmp_path))
    mock_client = MagicMock()
    mock_client.images.build.return_value = (MagicMock(id="sha256:abc"), [])
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container

    tag = build_image(mock_client, str(tmp_path))
    container = start_container(mock_client, tag, str(tmp_path))

    assert container is mock_container
    run_kwargs = mock_client.containers.run.call_args.kwargs
    assert run_kwargs["auto_remove"] is True
    assert run_kwargs["detach"] is True
    assert run_kwargs["mem_limit"] == "2g"
    assert run_kwargs["pids_limit"] == 256


def test_health_check_returns_true_on_200(tmp_path):
    mock_container = MagicMock()
    mock_container.ports = {f"{SANDBOX_PORT}/tcp": [{"HostPort": "18080"}]}

    with patch("smrt_agent.sandbox.lifecycle.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        result = health_check(mock_container, retries=1, delay=0)

    assert result is True


def test_health_check_returns_false_on_timeout(tmp_path):
    mock_container = MagicMock()
    mock_container.ports = {f"{SANDBOX_PORT}/tcp": [{"HostPort": "18080"}]}

    with patch("smrt_agent.sandbox.lifecycle.requests.get", side_effect=Exception("refused")):
        result = health_check(mock_container, retries=2, delay=0)

    assert result is False
