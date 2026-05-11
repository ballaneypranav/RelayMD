from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ClusterProvisioningState(SQLModel, table=True):
    cluster_name: str = Field(primary_key=True)
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utcnow_naive)
