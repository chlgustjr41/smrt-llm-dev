"""Runs API: create agent run, stream SSE events."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.agents.reviewer.loop import run_reviewer
from smrt_agent.api.deps import get_db
from smrt_agent.api.schemas import RunCreatedResponse
from smrt_agent.db.models import AgentRun, Project
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.event_log import EventLogger
from smrt_agent.settings import Settings

router = APIRouter(prefix="/projects", tags=["runs"])

# In-process queue registry: run_id -> asyncio.Queue
_queues: dict[str, asyncio.Queue] = {}


@router.post("/{project_id}/runs", status_code=202, response_model=RunCreatedResponse)
async def create_run(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunCreatedResponse:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    run_id = str(uuid.uuid4())
    agent_run = AgentRun(run_id=run_id, project_id=project_id, status="pending")
    db.add(agent_run)
    await db.commit()

    queue: asyncio.Queue = asyncio.Queue()
    _queues[run_id] = queue

    logged_queue = EventLogger(
        queue,
        Path(project.canonical_path) / ".smrt" / "runs" / f"{run_id}.jsonl",
    )

    settings = Settings()

    asyncio.create_task(
        _run_task(
            project_id=project_id,
            canonical_path=project.canonical_path,
            run_id=run_id,
            queue=logged_queue,
            api_key=settings.anthropic_api_key,
            model=settings.model_reviewer,
            budget_usd=settings.budget_per_run_usd,
        )
    )

    return RunCreatedResponse(run_id=run_id, status="pending")


async def _run_task(
    *,
    project_id: int,
    canonical_path: str,
    run_id: str,
    queue: asyncio.Queue,
    api_key: str,
    model: str,
    budget_usd: float,
) -> None:
    final_status = "error"
    try:
        # Update run status to running
        try:
            engine = get_engine(force_new=False)
            Session = get_session_factory(engine)
            async with Session() as db:
                result = await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
                run = result.scalar_one_or_none()
                if run:
                    run.status = "running"
                    run.started_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass  # DB status update is best-effort; don't block the agent

        await run_reviewer(
            project_path=Path(canonical_path),
            api_key=api_key,
            model=model,
            budget_usd=budget_usd,
            queue=queue,
        )
        final_status = "done"
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
        final_status = "error"
    finally:
        # Update final status in DB — also best-effort
        try:
            engine = get_engine(force_new=False)
            Session = get_session_factory(engine)
            async with Session() as db:
                result = await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
                run = result.scalar_one_or_none()
                if run:
                    run.status = final_status
                    run.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass


@router.get("/{project_id}/runs/{run_id}/events")
async def get_run_events(
    project_id: int,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    log_path = Path(project.canonical_path) / ".smrt" / "runs" / f"{run_id}.jsonl"
    if not log_path.exists():
        return {"events": []}
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return {"events": events}


@router.get("/{project_id}/runs/{run_id}/stream")
async def stream_run(project_id: int, run_id: str) -> StreamingResponse:
    queue = _queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error", "budget_exceeded"):
                    _queues.pop(run_id, None)
                    break
        except asyncio.TimeoutError:
            yield 'data: {"type": "timeout"}\n\n'
            _queues.pop(run_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
