from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smrt_agent.settings import Settings
from smrt_agent.db.session import get_engine
from smrt_agent.db.schema import init_schema
from smrt_agent.api.filesystem import router as filesystem_router
from smrt_agent.api.projects import router as projects_router
from smrt_agent.api.runs import router as runs_router
from smrt_agent.api.sandbox import router as sandbox_router
from smrt_agent.api.qa_sessions import router as qa_sessions_router
from smrt_agent.api.tickets import router as tickets_router
from smrt_agent.api.docs import router as docs_router
from smrt_agent.api.stats import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    await init_schema(engine)
    yield


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="SMRT Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://{settings.bind_host}:{settings.frontend_port}"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": app.version}

    app.include_router(filesystem_router)
    app.include_router(projects_router)
    app.include_router(sandbox_router)
    app.include_router(runs_router)
    app.include_router(qa_sessions_router)
    app.include_router(tickets_router)
    app.include_router(docs_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")

    return app


app = create_app()
