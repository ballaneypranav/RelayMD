from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import create_db_and_tables, dispose_engine, init_engine
from relaymd.orchestrator.routers.jobs_worker import router as jobs_worker_router
from relaymd.orchestrator.routers.workers import router as workers_router
from relaymd.orchestrator.scheduler import orphaned_job_requeue_loop, stale_worker_reaper_loop


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: OrchestratorSettings = app.state.settings
    init_engine(settings.database_url)
    await create_db_and_tables()

    stop_event = asyncio.Event()
    app.state.stop_event = stop_event
    app.state.background_tasks = []
    if app.state.start_background_tasks:
        reaper_task = asyncio.create_task(stale_worker_reaper_loop(settings, stop_event))
        orphaned_task = asyncio.create_task(orphaned_job_requeue_loop(stop_event))
        app.state.background_tasks = [reaper_task, orphaned_task]

    try:
        yield
    finally:
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
    app = FastAPI(lifespan=app_lifespan)
    app.state.settings = settings or OrchestratorSettings()
    app.state.start_background_tasks = start_background_tasks

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(workers_router)
    app.include_router(jobs_worker_router)

    return app


app = create_app()
