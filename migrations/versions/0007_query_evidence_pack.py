"""Typed structural query snapshots; historical traces remain legacy records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw1_query_runs",
        sa.Column("trace_schema_revision", sa.String(40), nullable=False, server_default="legacy-v1"),
    )
    op.add_column("cw1_query_runs", sa.Column("structural_snapshot", JSONB(), nullable=True))
    op.add_column("cw1_query_runs", sa.Column("evidence_pack", JSONB(), nullable=True))


def downgrade():
    raise RuntimeError("query_evidence_expand_only_use_compatible_application")
