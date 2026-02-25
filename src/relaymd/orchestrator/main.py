from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from relaymd.orchestrator import __version__
from relaymd.orchestrator.background_scheduler import build_background_scheduler
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import create_db_and_tables, dispose_engine, init_engine
from relaymd.orchestrator.logging import configure_logging, get_logger
from relaymd.orchestrator.routers.jobs_operator import router as jobs_operator_router
from relaymd.orchestrator.routers.jobs_worker import router as jobs_worker_router
from relaymd.orchestrator.routers.workers import router as workers_router

LOG = get_logger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: OrchestratorSettings = app.state.settings
    LOG.info("orchestrator_starting")
    init_engine(settings.database_url)
    await create_db_and_tables()

    app.state.scheduler = None
    if app.state.start_background_tasks:
        scheduler = build_background_scheduler(settings)
        scheduler.start()
        app.state.scheduler = scheduler

    try:
        yield
    finally:
        LOG.info("orchestrator_stopping")
        scheduler: AsyncIOScheduler | None = app.state.scheduler
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await dispose_engine()


def create_app(
    settings: OrchestratorSettings | None = None,
    *,
    start_background_tasks: bool = True,
) -> FastAPI:
    active_settings = settings or OrchestratorSettings()
    configure_logging(active_settings)
    config_paths = OrchestratorSettings.config_paths()
    LOG.info(
        "orchestrator_config_yaml",
        paths=[str(path) for path in config_paths],
        loaded=[path.is_file() for path in config_paths],
    )
    app = FastAPI(lifespan=app_lifespan)
    app.state.settings = active_settings
    app.state.start_background_tasks = start_background_tasks

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(workers_router)
    app.include_router(jobs_worker_router)
    app.include_router(jobs_operator_router)

    return app


app = create_app()


def start() -> None:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        uvicorn.main(
            args=["relaymd.orchestrator.main:app", *sys.argv[1:]],
            prog_name="relaymd-orchestrator",
        )
        return
    uvicorn.run("relaymd.orchestrator.main:app", host="0.0.0.0", port=8000)
