from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b2c3d4e5f678"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("job") as batch_op:
        batch_op.alter_column(
            "latest_checkpoint_path",
            new_column_name="latest_checkpoint_manifest_path",
            existing_type=sa.String(),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column("cancellation_requested_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_column("cancellation_requested_at")
        batch_op.alter_column(
            "latest_checkpoint_manifest_path",
            new_column_name="latest_checkpoint_path",
            existing_type=sa.String(),
            existing_nullable=True,
        )
