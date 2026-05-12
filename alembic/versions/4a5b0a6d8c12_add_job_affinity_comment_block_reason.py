"""Add job affinity/comment/blocking fields

Revision ID: 4a5b0a6d8c12
Revises: 9a6f9f5f8d21
Create Date: 2026-05-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a5b0a6d8c12"
down_revision: str | Sequence[str] | None = "9a6f9f5f8d21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("preferred_clusters_json", sa.String(), nullable=True))
    op.add_column("job", sa.Column("comment", sa.String(length=2000), nullable=True))
    op.add_column("job", sa.Column("queue_blocked_reason", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_column("queue_blocked_reason")
        batch_op.drop_column("comment")
        batch_op.drop_column("preferred_clusters_json")
