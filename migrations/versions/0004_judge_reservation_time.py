"""Account a delayed judge reservation in the month it actually starts."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw2_eval_cases", sa.Column("judge_reserved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("cw2_eval_cases", "judge_reserved_at")
