"""Persist required worker image keys on fresh profile-aware databases."""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_jobs = bind.execute(sa.text("SELECT COUNT(*) FROM job")).scalar_one()
    existing_workers = bind.execute(sa.text("SELECT COUNT(*) FROM worker")).scalar_one()
    if existing_jobs or existing_workers:
        raise RuntimeError(
            "RelayMD does not migrate pre-profile databases. Reset the database and "
            "configure worker_images before upgrading."
        )

    op.add_column("job", sa.Column("worker_image_key", sa.String(), nullable=True))
    op.add_column("worker", sa.Column("worker_image_key", sa.String(), nullable=True))
    with op.batch_alter_table("job") as batch_op:
        batch_op.alter_column("worker_image_key", nullable=False)
    with op.batch_alter_table("worker") as batch_op:
        batch_op.alter_column("worker_image_key", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("worker") as batch_op:
        batch_op.drop_column("worker_image_key")
    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_column("worker_image_key")
