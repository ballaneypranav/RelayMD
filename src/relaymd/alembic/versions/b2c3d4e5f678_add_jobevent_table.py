"""Add jobevent table and indexes

Revision ID: b2c3d4e5f678
Revises: 4a5b0a6d8c12
Create Date: 2026-05-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f678"
down_revision: str | Sequence[str] | None = "4a5b0a6d8c12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS jobevent (
            id INTEGER PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES job(id),
            occurred_at DATETIME NOT NULL,
            event_seq INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            worker_id TEXT,
            status_from TEXT,
            status_to TEXT,
            payload_json TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobevent_job_id ON jobevent (job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobevent_occurred_at ON jobevent (occurred_at)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_jobevent_job_seq ON jobevent (job_id, event_seq)"
    )


def downgrade() -> None:
    op.drop_table("jobevent")
