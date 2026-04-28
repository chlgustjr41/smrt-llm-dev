"""Shared SSE queue registry for all session types.

Both qa_sessions.py (QA discovery sessions) and tickets.py (ticket fix sessions)
register their queues here so the single qa-sessions stream endpoint can serve both.
"""
import asyncio

# Keyed by session_id (UUID). Populated by qa_sessions.py and tickets.py.
session_queues: dict[str, asyncio.Queue] = {}
