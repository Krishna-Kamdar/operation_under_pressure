"""Add an explicit unassigned activity event."""

from alembic import op

revision = "0002_add_unassigned_event"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE activity_event_type_enum ADD VALUE IF NOT EXISTS 'unassigned'"
    )


def downgrade() -> None:
    raise RuntimeError(
        "PostgreSQL enum values cannot be removed safely; restore the database "
        "from a pre-0002 backup instead."
    )
