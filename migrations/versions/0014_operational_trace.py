"""Nullable operational facts in the existing append-only Run event store."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw5_run_events", sa.Column("phase", sa.String(24)))
    op.add_column("cw5_run_events", sa.Column("current_fence", sa.Integer()))


def downgrade():
    raise RuntimeError("operational_receipts_are_durable_use_fix_forward")
