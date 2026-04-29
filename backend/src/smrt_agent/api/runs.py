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
from smrt_agent.agents import budget_gateway
from smrt_agent.docs.service import generate_docs as _generate_docs
from smrt_agent.knowledge import compute_doc_score, record_doc_score
from smrt_agent.api.deps import get_db
from smrt_agent.api.schemas import RunCreatedResponse
from smrt_agent.db.models import AgentRun, Project
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.event_log import EventLogger
from smrt_agent.llm import LLMClient
from smrt_agent.settings import Settings

router = APIRouter(prefix="/projects", tags=["runs"])

# In-process queue registry: run_id -> asyncio.Queue
_queues: dict[str, asyncio.Queue] = {}

# Background task registry: run_id -> asyncio.Task. Populated when a run is
# created so the cancel endpoint can call .cancel() on the running coroutine.
# Tasks are popped on completion via add_done_callback.
_tasks: dict[str, "asyncio.Task[None]"] = {}


@router.post("/{project_id}/runs", status_code=202, response_model=RunCreatedResponse)
async def create_run(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: dict | None = None,
) -> RunCreatedResponse:
    """Start an Init Audit run for a project.

    Optional body:
        {"generate_docs": bool}  — defaults to True. When False, the
        Reviewer skips README/docs generation and the post-run
        generate_docs() pass is skipped.

    The body is intentionally a free-form dict to keep this endpoint
    backward-compatible: existing callers that POST with no body still get
    the original behavior.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Default to True to preserve current behavior for any client that
    # hasn't been updated to the new contract.
    generate_docs_flag = True
    if isinstance(body, dict) and "generate_docs" in body:
        generate_docs_flag = bool(body["generate_docs"])

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

    task = asyncio.create_task(
        _run_task(
            project_id=project_id,
            canonical_path=project.canonical_path,
            run_id=run_id,
            queue=logged_queue,
            llm_client=LLMClient.from_project(project.config, settings),
            model=settings.model_reviewer,
            budget_usd=settings.budget_per_run_usd,
            job_id=run_id,
            generate_docs=generate_docs_flag,
        )
    )
    # Register so the cancel endpoint can find the task; auto-cleanup when
    # the task completes (whether normally or via cancellation).
    _tasks[run_id] = task
    task.add_done_callback(lambda _: _tasks.pop(run_id, None))

    return RunCreatedResponse(run_id=run_id, status="pending")


async def _run_task(
    *,
    project_id: int,
    canonical_path: str,
    run_id: str,
    queue: "EventLogger",
    llm_client: "LLMClient",
    model: str,
    budget_usd: float,
    job_id: str | None = None,
    generate_docs: bool = True,
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
            llm_client=llm_client,
            model=model,
            budget_usd=budget_usd,
            queue=queue,
            job_id=job_id,
            generate_docs=generate_docs,
        )
        final_status = "done"

        # Persist done status immediately — the "done" SSE event was just queued;
        # updating the DB here ensures listRuns refetches see the final status
        # before doc generation (which can take several seconds) begins.
        try:
            engine = get_engine(force_new=False)
            Session = get_session_factory(engine)
            async with Session() as db:
                result = await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
                run = result.scalar_one_or_none()
                if run:
                    run.status = "done"
                    run.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass

        # Generate docs after audit — best-effort, does not affect run status.
        # Skipped entirely when the user opted out of doc generation: the
        # post-run generator parses Project.md to produce module/endpoint
        # stubs in docs/, which would surprise a user who explicitly chose
        # an inspection-only run.
        if generate_docs:
            try:
                doc_counts = await _generate_docs(Path(canonical_path))
                await queue.put({
                    "type": "docs_written",
                    "backends": doc_counts["backends"],
                    "endpoints": doc_counts["endpoints"],
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                score_entry = compute_doc_score(Path(canonical_path))
                score_entry["ts"] = datetime.now(timezone.utc).isoformat()
                record_doc_score(Path(canonical_path), score_entry)
            except Exception as doc_exc:
                await queue.put({
                    "type": "docs_error",
                    "error": str(doc_exc),
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
        else:
            await queue.put({
                "type": "docs_skipped",
                "reason": "generate_docs flag was disabled for this run",
                "ts": datetime.now(timezone.utc).isoformat(),
            })
    except asyncio.CancelledError:
        # User clicked Cancel. The cancel endpoint already emitted a
        # `cancelled` SSE event and updated the DB row; we just stop
        # gracefully and re-raise so asyncio marks the task as cancelled.
        # The finally clause still runs and updates DB to "cancelled" if it
        # somehow wasn't set yet.
        final_status = "cancelled"
        raise
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
        final_status = "error"
    finally:
        # Update final status in DB for error cases (done is already committed above).
        if final_status != "done":
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


@router.post("/{project_id}/runs/{run_id}/cancel", status_code=200)
async def cancel_run(
    project_id: int,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Cancel a running Init Audit. Best-effort:
      - calls .cancel() on the background task (interrupts the LLM stream)
      - emits a `cancelled` event to the SSE stream so the UI updates live
      - marks the AgentRun status as 'cancelled' in the DB

    Idempotent: returns the current status even if the run already finished
    (no error — the user may click cancel slightly after a natural completion).
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task = _tasks.get(run_id)
    queue = _queues.get(run_id)

    cancelled = False
    if task and not task.done():
        task.cancel()
        cancelled = True
        if queue is not None:
            try:
                await queue.put({
                    "type": "cancelled",
                    "reason": "User requested cancellation",
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass

    # DB update — best-effort. The background task's finally block also writes
    # a final status, but we set it here too so the UI reflects the cancel
    # immediately (otherwise listRuns may briefly show "running" until the
    # task settles).
    try:
        result = await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
        run = result.scalar_one_or_none()
        if run and run.status in ("pending", "running"):
            run.status = "cancelled"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        pass

    return {"run_id": run_id, "cancelled": cancelled, "status": "cancelled"}


@router.post("/{project_id}/runs/{run_id}/budget-decision", status_code=200)
async def run_budget_decision(
    project_id: int,
    run_id: str,
    body: dict,
) -> dict:
    decision = body.get("decision", "terminate")
    found = budget_gateway.resolve(run_id, decision)
    if not found:
        raise HTTPException(status_code=409, detail="No budget pause pending for this run")
    return {"run_id": run_id, "decision": decision}


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
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"events": events}


@router.get("/{project_id}/runs/{run_id}/stream")
async def stream_run(project_id: int, run_id: str) -> StreamingResponse:
    queue = _queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error", "budget_exceeded", "cancelled"):
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
