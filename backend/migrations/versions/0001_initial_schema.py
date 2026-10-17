"""Create the initial Operations Under Pressure schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def enum(name: str, values: list[str]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in (
        ("role_enum", ["viewer", "member", "lead", "admin"]),
        ("work_item_type_enum", ["incident", "customer_issue", "payment", "compliance", "task"]),
        ("priority_enum", ["low", "medium", "high", "urgent"]),
        ("work_item_status_enum", ["open", "in_progress", "awaiting_approval", "resolved", "closed"]),
        (
            "activity_event_type_enum",
            ["created", "updated", "assigned", "priority_changed", "status_changed", "commented"],
        ),
        ("outbox_status_enum", ["pending", "processing", "completed", "failed"]),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    uuid_type = postgresql.UUID(as_uuid=True)
    now = sa.text("CURRENT_TIMESTAMP")
    op.create_table(
        "users",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "teams",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("name", name="uq_teams_name"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", uuid_type, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", enum("role_enum", ["viewer", "member", "lead", "admin"]), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("user_id", "team_id", name="uq_memberships_user_team"),
    )
    op.create_table(
        "work_items",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("item_type", enum("work_item_type_enum", ["incident", "customer_issue", "payment", "compliance", "task"]), nullable=False),
        sa.Column("priority", enum("priority_enum", ["low", "medium", "high", "urgent"]), nullable=False),
        sa.Column("status", enum("work_item_status_enum", ["open", "in_progress", "awaiting_approval", "resolved", "closed"]), nullable=False),
        sa.Column("team_id", uuid_type, sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignee_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("creator_id", uuid_type, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )
    op.create_index("ix_work_items_team_status_updated", "work_items", ["team_id", "status", "updated_at", "id"])
    op.create_index("ix_work_items_assignee_status", "work_items", ["assignee_id", "status", "updated_at", "id"])
    op.create_index("ix_work_items_priority_assignee", "work_items", ["priority", "assignee_id", "status"])
    op.create_index("ix_work_items_search_title", "work_items", ["title"])
    op.create_table(
        "activity_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("work_item_id", uuid_type, sa.ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", uuid_type, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", enum("activity_event_type_enum", ["created", "updated", "assigned", "priority_changed", "status_changed", "commented"]), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )
    op.create_index("ix_activity_events_item_created", "activity_events", ["work_item_id", "created_at", "id"])
    op.create_table(
        "comments",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("work_item_id", uuid_type, sa.ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", uuid_type, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )
    op.create_index("ix_comments_item_created", "comments", ["work_item_id", "created_at", "id"])
    op.create_table(
        "idempotency_keys",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("user_id", "operation", "key", name="uq_idempotency_user_operation_key"),
    )
    op.create_table(
        "outbox_jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", enum("outbox_status_enum", ["pending", "processing", "completed", "failed"]), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )
    op.create_index("ix_outbox_jobs_status_next_attempt", "outbox_jobs", ["status", "next_attempt_at", "created_at"])


def downgrade() -> None:
    for table in ("outbox_jobs", "idempotency_keys", "comments", "activity_events", "work_items", "memberships", "teams", "users"):
        op.drop_table(table)
    bind = op.get_bind()
    for name in ("outbox_status_enum", "activity_event_type_enum", "work_item_status_enum", "priority_enum", "work_item_type_enum", "role_enum"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
