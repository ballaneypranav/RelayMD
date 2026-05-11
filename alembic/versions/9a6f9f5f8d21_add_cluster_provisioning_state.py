"""Add cluster provisioning state table

Revision ID: 9a6f9f5f8d21
Revises: 3f3cb9e5c4f1
Create Date: 2026-05-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a6f9f5f8d21"
down_revision: str | Sequence[str] | None = "3f3cb9e5c4f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clusterprovisioningstate",
        sa.Column("cluster_name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("cluster_name"),
    )


def downgrade() -> None:
    op.drop_table("clusterprovisioningstate")
