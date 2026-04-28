"""
Root conftest.py — provides shared test fixtures for the inventory API test suite.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from db import db


@pytest_asyncio.fixture
async def client():
    """Async HTTP client wired directly to the FastAPI app. DB is reset per test."""
    db.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
