import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smrt_agent.main import create_app
from smrt_agent.db.schema import init_schema
from smrt_agent.api.deps import get_db


@pytest.fixture
async def test_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")  # disable allowlist in tests

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    app = create_app()

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_and_list_project(test_app, tmp_path):
    project_path = tmp_path / "myproject"
    project_path.mkdir()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/projects", json={"name": "myproject", "path": str(project_path)})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "myproject"
        assert data["id"] is not None

        list_resp = await client.get("/projects")
        assert list_resp.status_code == 200
        projects = list_resp.json()
        assert len(projects) == 1
        assert projects[0]["name"] == "myproject"


@pytest.mark.asyncio
async def test_register_duplicate_returns_409(test_app, tmp_path):
    project_path = tmp_path / "dupe"
    project_path.mkdir()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        await client.post("/projects", json={"name": "dupe", "path": str(project_path)})
        resp = await client.post("/projects", json={"name": "dupe", "path": str(project_path)})
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_outside_allowlist_returns_400(test_app, tmp_path, monkeypatch):
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "/allowed/root")
    project_path = tmp_path / "outside"
    project_path.mkdir()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/projects", json={"name": "outside", "path": str(project_path)})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_nonexistent_path_returns_400(test_app, tmp_path):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/projects", json={"name": "ghost", "path": str(tmp_path / "ghost")})
        assert resp.status_code == 400
