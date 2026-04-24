"""File watcher: triggers a QA session when project .py files change."""
import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable

from watchfiles import awatch

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 30.0


async def watch_project(
    project_id: int,
    canonical_path: str,
    trigger_fn: Callable[[int], Awaitable[None]],
) -> None:
    """Watch canonical_path for *.py changes and call trigger_fn with debounce."""
    path = Path(canonical_path)
    if not path.exists():
        logger.warning("Watch path does not exist: %s", canonical_path)
        return

    last_trigger: float = 0.0

    async for changes in awatch(str(path)):
        if not any(str(c[1]).endswith(".py") for c in changes):
            continue
        now = time.monotonic()
        if now - last_trigger >= _DEBOUNCE_SECONDS:
            logger.info("File change in project %d — triggering QA session", project_id)
            try:
                await trigger_fn(project_id)
                last_trigger = now
            except Exception as exc:
                logger.error("QA trigger failed for project %d: %s", project_id, exc)
