"""Finite evaluation and durable external outcomes; historical terminal facts stay intact."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    for name, default in {
        "execution_attempt": 0,
        "max_attempts": 3,
        "dispatch_generation": 0,
        "dispatch_count": 0,
        "dispatch_failures": 0,
        "admission_deferrals": 0,
        "max_admission_deferrals": 12,
        "fence": 0,
    }.items():
        op.add_column(
            "cw2_eval_cases", sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))
        )
    for name in (
        "next_attempt_at",
        "started_at",
        "completed_at",
        "absolute_deadline",
        "active_deadline",
        "cancel_requested_at",
    ):
        op.add_column("cw2_eval_cases", sa.Column(name, sa.DateTime(timezone=True)))
    for name, size in (("phase", 24), ("last_error_code", 80), ("last_error_category", 40)):
        op.add_column("cw2_eval_cases", sa.Column(name, sa.String(size)))
    op.add_column(
        "cw2_eval_runs",
        sa.Column("runtime_policy", sa.String(40), nullable=False, server_default="legacy-v1"),
    )
    for name in ("total_deadline", "cancel_requested_at"):
        op.add_column("cw2_eval_runs", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("cw2_eval_runs", sa.Column("completeness", JSONB(), nullable=False, server_default="{}"))
    # Only live work acquires a recovery policy; no fabricated historical attempts/phases.
    op.execute(
        "UPDATE cw2_eval_runs SET runtime_policy='eval-durable-v1', total_deadline=created_at + interval '4 hours' WHERE status IN ('PENDING','RUNNING')"
    )
    op.execute(
        "UPDATE cw2_eval_cases c SET absolute_deadline=r.total_deadline FROM cw2_eval_runs r WHERE c.eval_run_id=r.id AND c.status IN ('PENDING','QUEUED','RUNNING')"
    )
    # Table definitions are frozen here, independent of future ORM edits.
    op.create_table(
        "cw4_eval_outbox",
        sa.Column("eval_run_id", sa.Uuid(), sa.ForeignKey("cw2_eval_runs.id"), primary_key=True),
        sa.Column("case_id", sa.String(80), primary_key=True),
        sa.Column("dispatch_generation", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("next_send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.Integer(), nullable=False),
        sa.Column("publish_fence", sa.Integer(), nullable=False),
        sa.Column("publish_lease", sa.DateTime(timezone=True)),
        sa.Column("task_id", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["eval_run_id", "case_id"], ["cw2_eval_cases.eval_run_id", "cw2_eval_cases.case_id"]
        ),
    )
    op.create_table(
        "cw4_provider_phases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("eval_run_id", sa.Uuid(), sa.ForeignKey("cw2_eval_runs.id")),
        sa.Column("case_id", sa.String(80)),
        sa.Column("query_run_id", sa.Uuid(), sa.ForeignKey("cw1_query_runs.id")),
        sa.Column("logical_key", sa.String(200), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("phase_attempt", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("owner", sa.Uuid(), nullable=False),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_yuan", sa.Numeric(12, 8), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("request_id", sa.String(200)),
        sa.Column("usage", JSONB()),
        sa.Column("estimated_yuan", sa.Numeric(12, 8)),
        sa.Column("result_hash", sa.String(64)),
        sa.Column("result", JSONB()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("logical_key", "phase_attempt"),
        sa.CheckConstraint("phase_attempt BETWEEN 1 AND 2"),
        sa.ForeignKeyConstraint(
            ["eval_run_id", "case_id"], ["cw2_eval_cases.eval_run_id", "cw2_eval_cases.case_id"]
        ),
    )
    op.create_table(
        "cw4_provider_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phase_id", sa.Uuid(), sa.ForeignKey("cw4_provider_phases.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("detail", JSONB(), nullable=False),
    )


def downgrade():
    raise RuntimeError("provider_outcomes_are_durable_use_fix_forward")
