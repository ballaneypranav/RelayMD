import sqlalchemy as sa
from alembic import op

revision = "3f3cb9e5c4f1"
down_revision = "f8da36c3c972"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job", sa.Column("assigned_at", sa.DateTime(), nullable=True))
    op.add_column("job", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("job", sa.Column("status_changed_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE job SET status_changed_at = updated_at WHERE status_changed_at IS NULL")
    op.execute(
        "UPDATE job SET assigned_at = updated_at "
        "WHERE assigned_at IS NULL AND status IN ('assigned', 'running')"
    )
    with op.batch_alter_table("job") as batch_op:
        batch_op.alter_column("status_changed_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_column("status_changed_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("assigned_at")
