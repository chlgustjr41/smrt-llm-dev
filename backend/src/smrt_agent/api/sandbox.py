from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project
from smrt_agent.sandbox.exec import get_docker_client
from smrt_agent.sandbox.lifecycle import (
    build_image,
    generate_dockerfile,
    health_check,
    start_container,
)

router = APIRouter(prefix="/projects", tags=["sandbox"])


class SandboxStartResponse(BaseModel):
    container_id: str
    healthy: bool
    container_ip: str | None


@router.post("/{project_id}/sandbox/start", response_model=SandboxStartResponse)
async def start_sandbox(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SandboxStartResponse:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    canonical = project.canonical_path
    client = get_docker_client()

    generate_dockerfile(canonical)
    image_tag = build_image(client, canonical)
    container = start_container(client, image_tag, canonical)
    healthy = health_check(container)

    if not healthy:
        raise HTTPException(status_code=500, detail="Sandbox started but failed health-check")

    container.reload()
    networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
    from smrt_agent.sandbox.exec import SMRT_NETWORK
    net_info = networks.get(SMRT_NETWORK) or (next(iter(networks.values()), {}) if networks else {})
    container_ip = net_info.get("IPAddress")

    return SandboxStartResponse(
        container_id=container.id,
        healthy=healthy,
        container_ip=container_ip,
    )
