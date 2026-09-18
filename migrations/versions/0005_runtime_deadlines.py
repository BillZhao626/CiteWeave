"""Expand-only runtime foundations; historical terminal rows retain null semantics."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw1_ingestion_jobs", sa.Column("absolute_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("cw1_query_runs", sa.Column("absolute_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cw1_query_runs", sa.Column("owner", sa.Uuid(), nullable=True))
    op.add_column("cw1_query_runs", sa.Column("fence", sa.Integer(), nullable=True))
    op.add_column("cw1_query_runs", sa.Column("runtime_policy", sa.String(40), nullable=True))
    op.execute(
        "UPDATE cw1_ingestion_jobs SET absolute_deadline = created_at + interval '900 seconds' WHERE status IN ('PENDING','RETRY_WAIT','PARSING','CHUNKING','EMBEDDING','INDEXING')"
    )
    op.execute(
        "UPDATE cw1_query_runs SET absolute_deadline = created_at + interval '120 seconds' WHERE status = 'RUNNING'"
    )


def downgrade():
    raise RuntimeError("runtime_deadlines_expand_only_use_compatible_application")
