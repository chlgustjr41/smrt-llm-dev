import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smrt_agent.main import create_app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project
from smrt_agent.api.deps import get_db


@pytest.fixture
async def app_with_project(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed one project
    async with Session() as session:
        p = Project(name="todo-api", canonical_path=str(tmp_path / "todo"))
        session.add(p)
        await session.commit()
        await session.refresh(p)
        project_id = p.id

    app = create_app()

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_sandbox_returns_200_on_success(app_with_project):
    app, project_id = app_with_project

    mock_container = MagicMock()
    mock_container.id = "abc123"
    mock_container.ports = {"8080/tcp": [{"HostPort": "18080"}]}
    mock_container.reload = MagicMock()
    mock_container.attrs = {"NetworkSettings": {"Networks": {"smrt-internal": {"IPAddress": "172.20.0.5"}}}}

    with (
        patch("smrt_agent.api.sandbox.generate_dockerfile"),
        patch("smrt_agent.api.sandbox.build_image", return_value="smrt-sandbox-test"),
        patch("smrt_agent.api.sandbox.start_container", return_value=mock_container),
        patch("smrt_agent.api.sandbox.health_check", return_value=True),
        patch("smrt_agent.api.sandbox.get_docker_client", return_value=MagicMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/projects/{project_id}/sandbox/start")

    assert resp.status_code == 200
    body = resp.json()
    assert body["healthy"] is True
    assert body["container_id"] == "abc123"
    assert "container_ip" in body


@pytest.mark.asyncio
async def test_start_sandbox_returns_500_when_unhealthy(app_with_project):
    app, project_id = app_with_project

    mock_container = MagicMock()
    mock_container.id = "deadbeef"
    mock_container.ports = {"8080/tcp": [{"HostPort": "18081"}]}
    mock_container.reload = MagicMock()

    with (
        patch("smrt_agent.api.sandbox.generate_dockerfile"),
        patch("smrt_agent.api.sandbox.build_image", return_value="smrt-sandbox-test"),
        patch("smrt_agent.api.sandbox.start_container", return_value=mock_container),
        patch("smrt_agent.api.sandbox.health_check", return_value=False),
        patch("smrt_agent.api.sandbox.get_docker_client", return_value=MagicMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/projects/{project_id}/sandbox/start")

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_start_sandbox_404_for_unknown_project(app_with_project):
    app, _ = app_with_project
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/projects/9999/sandbox/start")
    assert resp.status_code == 404
