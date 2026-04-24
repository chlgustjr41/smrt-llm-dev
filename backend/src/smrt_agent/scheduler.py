"""APScheduler: nightly QA session per registered project at 03:00 local."""
import logging
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | BackgroundScheduler | None = None


def start_scheduler(
    trigger_fn: Callable[[int], Awaitable[None]],
    project_ids: list[int],
) -> AsyncIOScheduler | BackgroundScheduler:
    global _scheduler
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        _scheduler = AsyncIOScheduler()
    else:
        _scheduler = BackgroundScheduler()

    for project_id in project_ids:
        _scheduler.add_job(
            trigger_fn,
            CronTrigger(hour=3, minute=0),
            args=[project_id],
            id=f"nightly_qa_{project_id}",
        )
    _scheduler.start()
    logger.info("Scheduler started with %d nightly jobs", len(project_ids))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
