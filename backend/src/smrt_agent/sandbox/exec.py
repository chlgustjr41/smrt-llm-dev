"""Cross-platform Docker client factory and sandbox execution helper."""
import os
import sys
from typing import Any

import docker
from docker import DockerClient

SMRT_NETWORK = "smrt-internal"

# Resource caps applied to every sandbox container
SANDBOX_CPU_PERIOD = 100_000
SANDBOX_CPU_QUOTA = 200_000  # 2 CPUs
SANDBOX_MEM_LIMIT = "2g"
SANDBOX_PIDS_LIMIT = 256


def get_docker_client() -> DockerClient:
    """Return a Docker client, auto-detecting the socket path per platform."""
    host = os.getenv("DOCKER_HOST")
    if host:
        return docker.DockerClient(base_url=host)
    if sys.platform == "win32":
        return docker.DockerClient(base_url="npipe:////./pipe/docker_engine")
    return docker.from_env()


def run_in_sandbox(
    container_name: str,
    image: str,
    command: str | list[str],
    mounts: list[dict[str, Any]] | None = None,
    network: str = SMRT_NETWORK,
) -> Any:
    """Run a command in a named, ephemeral, resource-capped container."""
    client = get_docker_client()
    return client.containers.run(
        image=image,
        command=command,
        name=container_name,
        network=network,
        mounts=mounts or [],
        auto_remove=True,
        detach=True,
        cpu_period=SANDBOX_CPU_PERIOD,
        cpu_quota=SANDBOX_CPU_QUOTA,
        mem_limit=SANDBOX_MEM_LIMIT,
        pids_limit=SANDBOX_PIDS_LIMIT,
    )
