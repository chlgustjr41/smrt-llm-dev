"""EventLogger: wraps asyncio.Queue and tees every put() to a JSONL file."""
import asyncio
import json
from pathlib import Path


class EventLogger:
    """Wraps an asyncio.Queue, writing each event to a JSONL log file.

    The agent loops call put() on this wrapper. The SSE endpoints read
    directly from the inner queue. This tees events to persistent storage
    without changing the SSE streaming path.
    """

    def __init__(self, inner: asyncio.Queue, log_path: Path) -> None:
        self._inner = inner
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path = log_path

    async def put(self, item: dict) -> None:
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item) + "\n")
        await self._inner.put(item)

    def empty(self) -> bool:
        return self._inner.empty()

    def get_nowait(self) -> dict:
        return self._inner.get_nowait()
