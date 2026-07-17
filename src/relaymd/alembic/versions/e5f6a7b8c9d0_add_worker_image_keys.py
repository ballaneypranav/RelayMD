"""Persist the worker image compatibility key on jobs and workers."""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job", sa.Column("worker_image_key", sa.String(), nullable=True))
    op.add_column("worker", sa.Column("worker_image_key", sa.String(), nullable=True))
    op.execute("UPDATE job SET worker_image_key = 'atom-openmm' WHERE worker_image_key IS NULL")
    op.execute("UPDATE worker SET worker_image_key = 'atom-openmm' WHERE worker_image_key IS NULL")
    with op.batch_alter_table("job") as batch_op:
        batch_op.alter_column("worker_image_key", nullable=False)
    with op.batch_alter_table("worker") as batch_op:
        batch_op.alter_column("worker_image_key", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("worker") as batch_op:
        batch_op.drop_column("worker_image_key")
    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_column("worker_image_key")
