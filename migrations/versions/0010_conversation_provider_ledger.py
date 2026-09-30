"""Conversation ownership of the existing ledger; legacy rows remain untouched."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    table = "cw4_provider_phases"
    op.add_column(table, sa.Column("conversation_run_id", sa.Uuid()))
    op.create_foreign_key("fk_provider_conversation_run", table, "cw5_runs", ["conversation_run_id"], ["id"])
    for name, size in (
        ("provider", 80),
        ("model", 160),
        ("price_revision", 100),
        ("prompt_revision", 160),
        ("request_hash", 64),
    ):
        op.add_column(table, sa.Column(name, sa.String(size)))
    op.add_column(table, sa.Column("authorization_id", sa.Uuid()))
    op.add_column(table, sa.Column("authorization_deadline", sa.DateTime(timezone=True)))
    op.add_column(table, sa.Column("input_tokens", sa.Integer()))
    op.add_column(table, sa.Column("output_tokens", sa.Integer()))
    op.create_check_constraint(
        "ck_provider_conversation_owner",
        table,
        "conversation_run_id IS NULL OR (query_run_id IS NULL AND eval_run_id IS NULL AND case_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_provider_conversation_authorization",
        table,
        "conversation_run_id IS NULL OR ("
        "provider IS NOT NULL AND model IS NOT NULL AND price_revision IS NOT NULL AND "
        "authorization_id IS NOT NULL AND authorization_deadline IS NOT NULL AND "
        "input_tokens IS NOT NULL AND input_tokens > 0 AND "
        "output_tokens IS NOT NULL AND output_tokens > 0 AND reserved_yuan > 0 AND "
        "prompt_revision IS NOT NULL AND request_hash IS NOT NULL AND "
        "phase IN ('interpretation','generation') AND phase_attempt = 1)",
    )
    op.create_index(
        "uq_provider_conversation_purpose",
        table,
        ["conversation_run_id", "phase"],
        unique=True,
        postgresql_where=sa.text("conversation_run_id IS NOT NULL"),
    )
    op.create_index(
        "uq_provider_conversation_authorization",
        table,
        ["authorization_id"],
        unique=True,
        postgresql_where=sa.text("conversation_run_id IS NOT NULL"),
    )
    # No rebinding or retroactive pricing/authorization edits, even via another helper.
    # Legacy rows retain their existing ownership-transfer behavior.
    op.execute("""
    CREATE FUNCTION cw5_provider_identity_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.conversation_run_id IS NOT NULL OR NEW.conversation_run_id IS NOT NULL THEN
        IF ROW(OLD.conversation_run_id, OLD.query_run_id, OLD.eval_run_id, OLD.case_id,
               OLD.logical_key, OLD.phase, OLD.phase_attempt, OLD.owner, OLD.fence,
               OLD.provider, OLD.model, OLD.price_revision, OLD.authorization_id,
               OLD.authorization_deadline, OLD.input_tokens, OLD.output_tokens,
               OLD.prompt_revision, OLD.request_hash, OLD.reserved_yuan, OLD.reserved_at)
          IS DISTINCT FROM
           ROW(NEW.conversation_run_id, NEW.query_run_id, NEW.eval_run_id, NEW.case_id,
               NEW.logical_key, NEW.phase, NEW.phase_attempt, NEW.owner, NEW.fence,
               NEW.provider, NEW.model, NEW.price_revision, NEW.authorization_id,
               NEW.authorization_deadline, NEW.input_tokens, NEW.output_tokens,
               NEW.prompt_revision, NEW.request_hash, NEW.reserved_yuan, NEW.reserved_at)
        THEN RAISE EXCEPTION 'conversation_provider_identity_immutable' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw5_provider_identity_immutable BEFORE UPDATE ON cw4_provider_phases
      FOR EACH ROW EXECUTE FUNCTION cw5_provider_identity_immutable();
    """)


def downgrade():
    raise RuntimeError("provider_outcomes_are_durable_use_fix_forward")
