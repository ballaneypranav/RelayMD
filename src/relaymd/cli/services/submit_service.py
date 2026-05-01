from __future__ import annotations

from pathlib import Path

from relaymd_api_client.api.default import create_job_jobs_post
from relaymd_api_client.errors import UnexpectedStatus
from relaymd_api_client.models.job_create import JobCreate
from relaymd_api_client.models.job_read import JobRead

from relaymd.cli.context import CliContext


class SubmitService:
    def __init__(self, context: CliContext) -> None:
        self._context = context

    def _validate_storage_settings(self) -> None:
        settings = self._context.settings
        missing: list[tuple[str, str]] = []
        if not settings.b2_endpoint_url.strip():
            missing.append(("b2_endpoint_url", "B2_ENDPOINT_URL or B2_ENDPOINT"))
        if not settings.b2_bucket_name.strip():
            missing.append(("b2_bucket_name", "B2_BUCKET_NAME or BUCKET_NAME"))
        if not settings.b2_access_key_id.strip():
            missing.append(("b2_access_key_id", "B2_ACCESS_KEY_ID or B2_APPLICATION_KEY_ID"))
        if not settings.b2_secret_access_key.strip():
            missing.append(("b2_secret_access_key", "B2_SECRET_ACCESS_KEY or B2_APPLICATION_KEY"))

        if not missing:
            return

        details = ", ".join(f"{field} ({env_vars})" for field, env_vars in missing)
        hint = (
            " Set INFISICAL_TOKEN (or 'infisical_token' in config) to load secrets "
            "automatically, or provide the missing values directly via env vars or "
            "relaymd-config.yaml."
            if not self._context.settings.infisical_token.strip()
            else " Set env vars or update relaymd-config.yaml."
        )
        raise RuntimeError(f"Missing required B2 storage settings for submit: {details}.{hint}")

    def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
        self._validate_storage_settings()
        self._context.storage_client().upload_file(local_archive, b2_key)

    def register_job(self, *, job_id: str, title: str, b2_key: str) -> JobRead:
        try:
            with self._context.api_client() as client:
                body = JobCreate(id=job_id, title=title, input_bundle_path=b2_key)
                response = create_job_jobs_post.sync(
                    client=client,
                    body=body,
                    x_api_token=self._context.settings.api_token,
                )
        except UnexpectedStatus as exc:
            if exc.status_code == 404:
                orchestrator_url = self._context.settings.orchestrator_url.rstrip("/")
                raise RuntimeError(
                    "Job registration failed: POST /jobs returned 404 from "
                    f"{orchestrator_url}. This usually means the CLI is pointing at the wrong "
                    "orchestrator URL/port, or the running orchestrator is an older build that "
                    "does not expose job creation. Check 'orchestrator_url' and restart the "
                    "orchestrator from this checkout."
                ) from exc
            raise

        if response is None or not isinstance(response, JobRead):
            raise RuntimeError("Failed to parse create job response")
        return response
