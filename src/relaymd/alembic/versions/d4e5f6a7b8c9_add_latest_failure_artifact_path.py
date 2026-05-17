import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job", sa.Column("latest_failure_artifact_path", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_column("latest_failure_artifact_path")
