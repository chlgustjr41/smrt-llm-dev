from unittest.mock import MagicMock, patch
import pytest
from smrt_agent.sandbox.exec import (
    run_in_sandbox,
    SMRT_NETWORK,
    SANDBOX_CPU_PERIOD,
    SANDBOX_CPU_QUOTA,
    SANDBOX_MEM_LIMIT,
    SANDBOX_PIDS_LIMIT,
)


def test_run_in_sandbox_passes_resource_caps():
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container

    with patch("smrt_agent.sandbox.exec.get_docker_client", return_value=mock_client):
        result = run_in_sandbox(
            container_name="test-box",
            image="python:3.11-slim",
            command=["python", "-c", "print('hello')"],
        )

    assert result is mock_container
    call_kwargs = mock_client.containers.run.call_args.kwargs
    assert call_kwargs["name"] == "test-box"
    assert call_kwargs["network"] == SMRT_NETWORK
    assert call_kwargs["auto_remove"] is True
    assert call_kwargs["detach"] is True
    assert call_kwargs["cpu_period"] == SANDBOX_CPU_PERIOD
    assert call_kwargs["cpu_quota"] == SANDBOX_CPU_QUOTA
    assert call_kwargs["mem_limit"] == SANDBOX_MEM_LIMIT
    assert call_kwargs["pids_limit"] == SANDBOX_PIDS_LIMIT


def test_run_in_sandbox_accepts_custom_network():
    mock_client = MagicMock()
    with patch("smrt_agent.sandbox.exec.get_docker_client", return_value=mock_client):
        run_in_sandbox(
            container_name="test-box",
            image="python:3.11-slim",
            command="echo hi",
            network="custom-net",
        )
    call_kwargs = mock_client.containers.run.call_args.kwargs
    assert call_kwargs["network"] == "custom-net"
