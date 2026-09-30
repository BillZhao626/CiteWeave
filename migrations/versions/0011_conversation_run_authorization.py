"""Immutable generic aggregate Run authorization; no implicit legacy grants."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    table = "cw5_runs"
    for name, kind in (
        ("authorization_id", sa.Uuid()),
        ("authorization_deadline", sa.DateTime(timezone=True)),
        ("authorization_max_calls", sa.Integer()),
        ("authorization_input_tokens", sa.BigInteger()),
        ("authorization_output_tokens", sa.BigInteger()),
        ("authorization_yuan", sa.Numeric(12, 8)),
    ):
        op.add_column(table, sa.Column(name, kind, nullable=True))
    op.create_unique_constraint("uq_conversation_run_authorization", table, ["authorization_id"])
    op.create_check_constraint(
        "ck_conversation_run_authorization",
        table,
        "(authorization_id IS NULL AND authorization_deadline IS NULL AND "
        "authorization_max_calls IS NULL AND authorization_input_tokens IS NULL AND "
        "authorization_output_tokens IS NULL AND authorization_yuan IS NULL) OR "
        "(authorization_id IS NOT NULL AND authorization_deadline IS NOT NULL AND "
        "authorization_max_calls IS NOT NULL AND authorization_max_calls >= 0 AND "
        "authorization_input_tokens IS NOT NULL AND authorization_input_tokens >= 0 AND "
        "authorization_output_tokens IS NOT NULL AND authorization_output_tokens >= 0 AND "
        "authorization_yuan IS NOT NULL AND authorization_yuan >= 0)",
    )
    op.execute("""
    CREATE FUNCTION cw5_run_authorization_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.authorization_id IS NOT NULL AND
        ROW(OLD.id, OLD.conversation_id, OLD.turn_id, OLD.owner, OLD.fence,
            OLD.authorization_id, OLD.authorization_deadline, OLD.authorization_max_calls,
            OLD.authorization_input_tokens, OLD.authorization_output_tokens, OLD.authorization_yuan)
        IS DISTINCT FROM
        ROW(NEW.id, NEW.conversation_id, NEW.turn_id, NEW.owner, NEW.fence,
            NEW.authorization_id, NEW.authorization_deadline, NEW.authorization_max_calls,
            NEW.authorization_input_tokens, NEW.authorization_output_tokens, NEW.authorization_yuan)
      THEN RAISE EXCEPTION 'conversation_run_authorization_immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw5_run_authorization_immutable BEFORE UPDATE ON cw5_runs
      FOR EACH ROW EXECUTE FUNCTION cw5_run_authorization_immutable();
    """)


def downgrade():
    raise RuntimeError("run_authorizations_are_durable_use_fix_forward")
