"""Sandbox lifecycle: Dockerfile generation, image build, container start, health-check."""
import hashlib
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from docker import DockerClient

from smrt_agent.sandbox.exec import (
    SANDBOX_CPU_PERIOD,
    SANDBOX_CPU_QUOTA,
    SANDBOX_MEM_LIMIT,
    SANDBOX_PIDS_LIMIT,
    SMRT_NETWORK,
)

SANDBOX_PORT = 8080

_DOCKERFILE_TEMPLATE = """\
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt --no-cache-dir
EXPOSE {port}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
""".format(port=SANDBOX_PORT)


def generate_dockerfile(canonical_path: str) -> Path:
    """Return the Dockerfile path (written to a temp staging area, not inside the project)."""
    path_hash = hashlib.sha1(canonical_path.encode()).hexdigest()[:12]
    staging = Path(tempfile.gettempdir()) / "smrt-sandbox" / path_hash
    staging.mkdir(parents=True, exist_ok=True)
    df = staging / "Dockerfile"
    df.write_text(_DOCKERFILE_TEMPLATE)
    return df


def build_image(docker_client: DockerClient, canonical_path: str) -> str:
    """Build a Docker image from the project source. Returns the image tag."""
    path_hash = hashlib.sha1(canonical_path.encode()).hexdigest()[:12]
    tag = f"smrt-sandbox-{path_hash}"

    staging = Path(tempfile.gettempdir()) / "smrt-sandbox" / path_hash
    staging.mkdir(parents=True, exist_ok=True)

    # Copy project source into the staging build context
    for item in Path(canonical_path).iterdir():
        if item.name in (".smrt", ".venv", "__pycache__", ".git", "node_modules"):
            continue
        dest = staging / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Write Dockerfile into staging context if not already there
    df = staging / "Dockerfile"
    if not df.exists():
        df.write_text(_DOCKERFILE_TEMPLATE)

    docker_client.images.build(
        path=str(staging),
        tag=tag,
        rm=True,
        quiet=True,
    )
    return tag


def start_container(docker_client: DockerClient, image_tag: str, canonical_path: str) -> Any:
    """Start an ephemeral, resource-capped sandbox container. Returns the container object."""
    path_hash = hashlib.sha1(canonical_path.encode()).hexdigest()[:12]
    container_name = f"smrt-run-{path_hash}"

    # Remove any existing container with this name before starting
    try:
        old = docker_client.containers.get(container_name)
        old.remove(force=True)
    except Exception:
        pass

    return docker_client.containers.run(
        image=image_tag,
        name=container_name,
        network=SMRT_NETWORK,
        auto_remove=True,
        detach=True,
        cpu_period=SANDBOX_CPU_PERIOD,
        cpu_quota=SANDBOX_CPU_QUOTA,
        mem_limit=SANDBOX_MEM_LIMIT,
        pids_limit=SANDBOX_PIDS_LIMIT,
    )


def health_check(container: Any, retries: int = 30, delay: float = 0.5) -> bool:
    """Poll the container's /health endpoint via its IP on smrt-internal network."""
    for _ in range(retries):
        try:
            container.reload()
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            net_info = networks.get(SMRT_NETWORK) or (next(iter(networks.values()), {}) if networks else {})
            ip = net_info.get("IPAddress", "")
            if ip:
                resp = requests.get(f"http://{ip}:{SANDBOX_PORT}/health", timeout=2)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        if delay:
            time.sleep(delay)
    return False
