"""worker: add status, rename slurm_job_id to provider_id

Revision ID: a1b2c3d4e5f6
Revises: 51c343ab81c6
Create Date: 2026-02-28 22:04:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "51c343ab81c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename slurm_job_id -> provider_id and add status column.

    Backfill:
    - Existing rows with slurm_job_id containing ':' are placeholder workers
      submitted to SLURM but not yet started.  Their provider_id stays as-is
      (the "cluster:id" format is now the canonical provider_id for SLURM workers),
      and their status is set to 'queued'.
    - All other rows are active workers; status defaults to 'active'.
    """
    # SQLite doesn't support ALTER COLUMN RENAME natively; use batch mode.
    with op.batch_alter_table("worker") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.Enum("queued", "active", name="workerstatus"),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.alter_column(
            "slurm_job_id",
            new_column_name="provider_id",
            existing_type=sa.String(),
            existing_nullable=True,
        )

    # Backfill: rows that were placeholder workers have ':' in the old slurm_job_id
    # (now provider_id).  Mark them as queued.
    op.execute(
        "UPDATE worker SET status = 'queued' WHERE provider_id LIKE '%:%'"
    )


def downgrade() -> None:
    """Reverse: rename provider_id -> slurm_job_id, drop status."""
    with op.batch_alter_table("worker") as batch_op:
        batch_op.alter_column(
            "provider_id",
            new_column_name="slurm_job_id",
            existing_type=sa.String(),
            existing_nullable=True,
        )
        batch_op.drop_column("status")
