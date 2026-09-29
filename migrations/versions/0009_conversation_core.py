"""Additive conversation authority; no legacy backfill or destructive downgrade."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw5_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("head_id", sa.Uuid()),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "key"),
        sa.CheckConstraint("fence >= 0", name="ck_conversation_fence"),
    )
    op.create_table(
        "cw5_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("cw5_conversations.id"), nullable=False),
        sa.Column("expected_head", sa.Uuid()),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("conversation_id", "id"),
    )
    op.create_table(
        "cw5_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("cw5_conversations.id"), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("retry_of", sa.Uuid()),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("owner", sa.Uuid(), nullable=False),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("conversation_id", "key"),
        sa.UniqueConstraint("conversation_id", "turn_id", "id"),
        sa.UniqueConstraint("retry_of"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "turn_id"], ["cw5_turns.conversation_id", "cw5_turns.id"]
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "turn_id", "retry_of"],
            ["cw5_runs.conversation_id", "cw5_runs.turn_id", "cw5_runs.id"],
        ),
        sa.CheckConstraint("fence > 0", name="ck_conversation_run_fence"),
        sa.CheckConstraint(
            "status IN ('ADMITTED','ACCEPTED','FAILED','CANCELLED','INTERRUPTED','UNKNOWN','STALE')",
            name="ck_conversation_run_status",
        ),
        sa.CheckConstraint(
            "(status = 'ADMITTED') = (completed_at IS NULL)", name="ck_conversation_run_completion"
        ),
    )
    op.create_index(
        "uq_conversation_active_run",
        "cw5_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ADMITTED'"),
    )
    op.create_index("ix_conversation_turn_runs", "cw5_runs", ["turn_id"])
    op.create_table(
        "cw5_acceptances",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("cw5_conversations.id"), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("state", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("turn_id"),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint("conversation_id", "id"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "turn_id", "run_id"],
            ["cw5_runs.conversation_id", "cw5_runs.turn_id", "cw5_runs.id"],
        ),
    )
    op.create_foreign_key(
        "fk_conversation_head",
        "cw5_conversations",
        "cw5_acceptances",
        ["id", "head_id"],
        ["conversation_id", "id"],
    )
    op.create_foreign_key(
        "fk_turn_input_snapshot",
        "cw5_turns",
        "cw5_acceptances",
        ["conversation_id", "expected_head"],
        ["conversation_id", "id"],
    )


def downgrade():
    raise RuntimeError("conversation_history_is_durable_use_fix_forward_or_matching_backup")
