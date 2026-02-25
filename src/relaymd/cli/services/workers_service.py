from __future__ import annotations

from relaymd_api_client.api.default import list_workers_workers_get
from relaymd_api_client.models.worker_read import WorkerRead

from relaymd.cli.context import CliContext


class WorkersService:
    def __init__(self, context: CliContext) -> None:
        self._context = context

    def list_workers(self) -> list[WorkerRead]:
        with self._context.api_client() as client:
            workers = list_workers_workers_get.sync(
                client=client,
                x_api_token=self._context.settings.api_token,
            )
        if workers is None or not isinstance(workers, list):
            raise RuntimeError("Failed to parse list workers response")
        if workers and not isinstance(workers[0], WorkerRead):
            raise RuntimeError("Unexpected response model for list workers")
        return workers
