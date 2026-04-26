"""EventLogger: wraps asyncio.Queue and tees every put() to a JSONL file."""
import asyncio
import json
from pathlib import Path


class EventLogger:
    """Wraps an asyncio.Queue, writing each event to a JSONL log file.

    The agent loops call put() on this wrapper. The SSE endpoints read
    directly from the inner queue. This tees events to persistent storage
    without changing the SSE streaming path.

    File I/O is offloaded to a thread via asyncio.to_thread so that the
    event loop is never blocked — even when the agent emits dozens of
    text_delta events per second.
    """

    def __init__(self, inner: asyncio.Queue, log_path: Path) -> None:
        self._inner = inner
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path = log_path

    def _append(self, line: str) -> None:
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    async def put(self, item: dict) -> None:
        await asyncio.to_thread(self._append, json.dumps(item) + "\n")
        await self._inner.put(item)

    def empty(self) -> bool:
        return self._inner.empty()

    def get_nowait(self) -> dict:
        return self._inner.get_nowait()
