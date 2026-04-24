"""Sandbox lifecycle: Dockerfile generation, image build, container start, health-check."""
import hashlib
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
    """Write a sandbox Dockerfile next to the project at <path>/.smrt/sandbox/Dockerfile."""
    sandbox_dir = Path(canonical_path) / ".smrt" / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    df = sandbox_dir / "Dockerfile"
    df.write_text(_DOCKERFILE_TEMPLATE)
    return df


def build_image(docker_client: DockerClient, canonical_path: str) -> str:
    """Build a Docker image from the project's sandbox Dockerfile. Returns the image tag."""
    path_hash = hashlib.sha1(canonical_path.encode()).hexdigest()[:12]
    tag = f"smrt-sandbox-{path_hash}"

    sandbox_dir = Path(canonical_path) / ".smrt" / "sandbox"
    # Copy project source into sandbox build context
    build_ctx = sandbox_dir / "context"
    build_ctx.mkdir(exist_ok=True)

    import shutil
    for item in Path(canonical_path).iterdir():
        if item.name in (".smrt", ".venv", "__pycache__", ".git"):
            continue
        dest = build_ctx / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Copy Dockerfile into context
    shutil.copy2(sandbox_dir / "Dockerfile", build_ctx / "Dockerfile")

    docker_client.images.build(
        path=str(build_ctx),
        tag=tag,
        rm=True,
        quiet=True,
    )
    return tag


def start_container(docker_client: DockerClient, image_tag: str, canonical_path: str) -> Any:
    """Start an ephemeral, resource-capped sandbox container. Returns the container object."""
    path_hash = hashlib.sha1(canonical_path.encode()).hexdigest()[:12]
    container_name = f"smrt-run-{path_hash}"

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
        ports={f"{SANDBOX_PORT}/tcp": None},  # dynamic host port
    )


def health_check(container: Any, retries: int = 30, delay: float = 0.5) -> bool:
    """Poll the container's /health endpoint until 200 or retries exhausted."""
    container.reload()
    port_bindings = container.ports.get(f"{SANDBOX_PORT}/tcp") or []
    host_port = port_bindings[0]["HostPort"] if port_bindings else str(SANDBOX_PORT)

    for _ in range(retries):
        try:
            resp = requests.get(f"http://127.0.0.1:{host_port}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        if delay:
            time.sleep(delay)
    return False
