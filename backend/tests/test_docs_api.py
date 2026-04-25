import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from smrt_agent.main import app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project
from smrt_agent.api.deps import get_db


@pytest.fixture
async def test_app_with_docs(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        proj = Project(name="todo-api", canonical_path=str(tmp_path))
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        project_id = proj.id

    # Create some doc files in the project path
    docs_api = tmp_path / "docs" / "api"
    docs_api.mkdir(parents=True)
    (docs_api / "GET_items.md").write_text("# GET /items", encoding="utf-8")
    (docs_api / "index.md").write_text("# API Reference", encoding="utf-8")

    wiki_api = tmp_path / "wiki" / "api"
    wiki_api.mkdir(parents=True)
    (wiki_api / "GET_items.md").write_text("---\ntype: endpoint\n---\n# GET /items", encoding="utf-8")

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id, tmp_path
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_docs_returns_files(test_app_with_docs):
    test_app, project_id, _ = test_app_with_docs
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    paths = [f["path"] for f in data["files"]]
    assert any("docs/api/GET_items.md" in p for p in paths)
    assert any("wiki/api/GET_items.md" in p for p in paths)


@pytest.mark.asyncio
async def test_list_docs_backend_field(test_app_with_docs):
    test_app, project_id, _ = test_app_with_docs
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/docs")
    files = resp.json()["files"]
    backends = {f["backend"] for f in files}
    assert "github" in backends
    assert "obsidian" in backends


@pytest.mark.asyncio
async def test_list_docs_404_for_unknown_project(test_app_with_docs):
    test_app, _, _ = test_app_with_docs
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/projects/99999/docs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_docs_empty_when_no_dirs(test_app_with_docs):
    test_app, _, tmp_path = test_app_with_docs
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    empty_path = tmp_path / "empty"
    empty_path.mkdir()
    async with Session() as session:
        proj2 = Project(name="empty-project", canonical_path=str(empty_path))
        session.add(proj2)
        await session.commit()
        await session.refresh(proj2)
        proj2_id = proj2.id
    await engine.dispose()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{proj2_id}/docs")
    assert resp.status_code == 200
    assert resp.json()["files"] == []
