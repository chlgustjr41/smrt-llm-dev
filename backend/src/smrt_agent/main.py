from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smrt_agent.settings import Settings
from smrt_agent.db.session import get_engine
from smrt_agent.db.schema import init_schema
from smrt_agent.api.projects import router as projects_router
from smrt_agent.api.runs import router as runs_router
from smrt_agent.api.sandbox import router as sandbox_router


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

    app.include_router(projects_router)
    app.include_router(sandbox_router)
    app.include_router(runs_router)

    return app


app = create_app()
