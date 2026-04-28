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
from smrt_agent.api.session_registry import session_queues
from smrt_agent.agents import budget_gateway
from smrt_agent.db.models import Project, QASession
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.event_log import EventLogger
from smrt_agent.llm import LLMClient
from smrt_agent.settings import Settings
from smrt_agent.agents.orchestrator import run_qa_session

router = APIRouter(prefix="/projects", tags=["qa-sessions"])

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
    session_queues[session_id] = queue

    logged_queue = EventLogger(
        queue,
        Path(project.canonical_path) / ".smrt" / "qa-sessions" / f"{session_id}.jsonl",
    )

    settings = Settings()
    import json as _json
    try:
        stored = _json.loads(project.config or '{}')
    except Exception:
        stored = {}

    asyncio.create_task(_session_task(
        project_id=project_id,
        session_id=session_id,
        canonical_path=project.canonical_path,
        queue=logged_queue,
        llm_client=LLMClient.from_project(project.config, settings),
        model_qa=stored.get("qa_model", settings.model_qa),
        model_coder=stored.get("coder_model", settings.model_coder),
        budget_usd=settings.budget_per_run_usd,
        max_fix_attempts=stored.get("max_fix_attempts", settings.max_fix_attempts),
        max_questions_per_attempt=stored.get("max_questions_per_attempt", 0),
        job_id=session_id,
    ))

    return {"session_id": session_id, "status": "pending"}


async def _session_task(
    *, project_id: int, session_id: str, canonical_path: str,
    queue: "EventLogger", llm_client: "LLMClient", model_qa: str, model_coder: str,
    budget_usd: float, max_fix_attempts: int, max_questions_per_attempt: int = 0,
    job_id: str | None = None,
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
            llm_client=llm_client,
            model_qa=model_qa,
            model_coder=model_coder,
            budget_usd=budget_usd,
            queue=queue,
            job_id=job_id,
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


@router.get("/{project_id}/qa-sessions/latest")
async def get_latest_qa_session(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the most recent full QA session (ticket_id IS NULL) for a project.

    Used by the Overview tab to hydrate the QA/Test Session card on page load
    so users don't lose context when switching tabs.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id.is_(None))
        .order_by(QASession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return {"session_id": None, "status": None, "started_at": None, "completed_at": None}
    return {
        "session_id": session.session_id,
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
    }


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
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"events": events}


@router.get("/{project_id}/qa-sessions/{session_id}/stream")
async def stream_qa_session(project_id: int, session_id: str) -> StreamingResponse:
    queue = session_queues.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Session not found or already completed")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error", "budget_exceeded"):
                    session_queues.pop(session_id, None)
                    break
        except asyncio.TimeoutError:
            yield 'data: {"type": "timeout"}\n\n'
            session_queues.pop(session_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{project_id}/qa-sessions/{session_id}/budget-decision", status_code=200)
async def qa_session_budget_decision(
    project_id: int,
    session_id: str,
    body: dict,
) -> dict:
    decision = body.get("decision", "terminate")
    found = budget_gateway.resolve(session_id, decision)
    if not found:
        raise HTTPException(status_code=409, detail="No budget pause pending for this session")
    return {"session_id": session_id, "decision": decision}


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
