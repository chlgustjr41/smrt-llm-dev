"""QA sessions API: create, stream SSE, approve/skip HITL."""
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

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project, QASession
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.event_log import EventLogger
from smrt_agent.settings import Settings
from smrt_agent.agents.orchestrator import run_qa_session

router = APIRouter(prefix="/projects", tags=["qa-sessions"])

_queues: dict[str, asyncio.Queue] = {}
_hitl_events: dict[str, asyncio.Event] = {}
_hitl_decisions: dict[str, str] = {}


@router.post("/{project_id}/qa-sessions", status_code=202)
async def create_qa_session(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    session_id = str(uuid.uuid4())
    qa_session = QASession(session_id=session_id, project_id=project_id, status="pending")
    db.add(qa_session)
    await db.commit()

    queue: asyncio.Queue = asyncio.Queue()
    _queues[session_id] = queue

    logged_queue = EventLogger(
        queue,
        Path(project.canonical_path) / ".smrt" / "qa-sessions" / f"{session_id}.jsonl",
    )

    settings = Settings()

    asyncio.create_task(_session_task(
        project_id=project_id,
        session_id=session_id,
        canonical_path=project.canonical_path,
        queue=logged_queue,
        api_key=settings.anthropic_api_key,
        model_qa=settings.model_qa,
        model_coder=settings.model_coder,
        budget_usd=settings.budget_per_run_usd,
        max_fix_attempts=settings.max_fix_attempts,
    ))

    return {"session_id": session_id, "status": "pending"}


async def _session_task(
    *, project_id: int, session_id: str, canonical_path: str,
    queue: asyncio.Queue, api_key: str, model_qa: str, model_coder: str,
    budget_usd: float, max_fix_attempts: int,
) -> None:
    final_status = "error"
    try:
        engine = get_engine(force_new=False)
        Session = get_session_factory(engine)
        async with Session() as db:
            result = await db.execute(select(QASession).where(QASession.session_id == session_id))
            sess = result.scalar_one_or_none()
            if sess:
                sess.status = "qa_running"
                sess.started_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:
        pass

    try:
        final_status = await run_qa_session(
            session_id=session_id,
            project_path=Path(canonical_path),
            api_key=api_key,
            model_qa=model_qa,
            model_coder=model_coder,
            budget_usd=budget_usd,
            max_fix_attempts=max_fix_attempts,
            queue=queue,
            hitl_events=_hitl_events,
            hitl_decisions=_hitl_decisions,
        )
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
        final_status = "error"
    finally:
        try:
            engine = get_engine(force_new=False)
            Session = get_session_factory(engine)
            async with Session() as db:
                result = await db.execute(select(QASession).where(QASession.session_id == session_id))
                sess = result.scalar_one_or_none()
                if sess:
                    sess.status = final_status
                    sess.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
        await queue.put({"type": "done", "status": final_status})


@router.get("/{project_id}/qa-sessions/{session_id}/events")
async def get_qa_session_events(
    project_id: int,
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    log_path = Path(project.canonical_path) / ".smrt" / "qa-sessions" / f"{session_id}.jsonl"
    if not log_path.exists():
        return {"events": []}
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return {"events": events}


@router.get("/{project_id}/qa-sessions/{session_id}/stream")
async def stream_qa_session(project_id: int, session_id: str) -> StreamingResponse:
    queue = _queues.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Session not found or already completed")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error", "budget_exceeded"):
                    _queues.pop(session_id, None)
                    break
        except asyncio.TimeoutError:
            yield 'data: {"type": "timeout"}\n\n'
            _queues.pop(session_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{project_id}/qa-sessions/{session_id}/approve", status_code=200)
async def approve_qa_session(project_id: int, session_id: str) -> dict:
    event = _hitl_events.get(session_id)
    if event is None:
        raise HTTPException(status_code=409, detail="No HITL request pending for this session")
    _hitl_decisions[session_id] = "approve"
    event.set()
    return {"decision": "approve"}


@router.post("/{project_id}/qa-sessions/{session_id}/skip", status_code=200)
async def skip_qa_session(project_id: int, session_id: str) -> dict:
    event = _hitl_events.get(session_id)
    if event is None:
        raise HTTPException(status_code=409, detail="No HITL request pending for this session")
    _hitl_decisions[session_id] = "skip"
    event.set()
    return {"decision": "skip"}
