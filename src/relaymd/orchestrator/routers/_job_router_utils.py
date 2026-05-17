from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job


async def get_job_or_404(session: AsyncSession, job_id: UUID) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def model_fields_dict(payload: Any, fields: tuple[str, ...]) -> dict[str, object]:
    return {
        field_name: getattr(payload, field_name)
        for field_name in fields
        if field_name in payload.model_fields_set
    }
