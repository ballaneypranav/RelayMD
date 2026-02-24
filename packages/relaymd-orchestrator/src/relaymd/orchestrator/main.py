from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from relaymd.orchestrator import __version__
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import create_db_and_tables, dispose_engine, init_engine
from relaymd.orchestrator.logging import configure_logging, get_logger
from relaymd.orchestrator.routers.jobs_operator import router as jobs_operator_router
from relaymd.orchestrator.routers.jobs_worker import router as jobs_worker_router
from relaymd.orchestrator.routers.workers import router as workers_router
from relaymd.orchestrator.scheduler import (
    orphaned_job_requeue_loop,
    sbatch_submission_loop,
    stale_worker_reaper_loop,
)

LOG = get_logger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: OrchestratorSettings = app.state.settings
    LOG.info("orchestrator_starting")
    init_engine(settings.database_url)
    await create_db_and_tables()

    stop_event = asyncio.Event()
    app.state.stop_event = stop_event
    app.state.background_tasks = []
    if app.state.start_background_tasks:
        reaper_task = asyncio.create_task(stale_worker_reaper_loop(settings, stop_event))
        orphaned_task = asyncio.create_task(orphaned_job_requeue_loop(stop_event))
        sbatch_task = asyncio.create_task(sbatch_submission_loop(settings, stop_event))
        app.state.background_tasks = [reaper_task, orphaned_task, sbatch_task]

    try:
        yield
    finally:
        LOG.info("orchestrator_stopping")
        stop_event.set()
        for task in app.state.background_tasks:
            task.cancel()
        await asyncio.gather(*app.state.background_tasks, return_exceptions=True)
        await dispose_engine()


def create_app(
    settings: OrchestratorSettings | None = None,
    *,
    start_background_tasks: bool = True,
) -> FastAPI:
    active_settings = settings or OrchestratorSettings()
    configure_logging(active_settings)
    config_path = OrchestratorSettings.config_path()
    LOG.info("orchestrator_config_yaml", path=str(config_path), loaded=config_path.is_file())
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
