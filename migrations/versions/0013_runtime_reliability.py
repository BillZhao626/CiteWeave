"""Bounded retries, once-only execution and durable reliability evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw5_runs", sa.Column("execution_started_at", sa.DateTime(timezone=True)))
    phase = "cw4_provider_phases"
    op.add_column(phase, sa.Column("transport_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(phase, sa.Column("transport_attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(phase, sa.Column("retry_classification", sa.String(24)))
    op.add_column(phase, sa.Column("retry_after", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_provider_transport_attempt",
        phase,
        "transport_limit BETWEEN 1 AND 3 AND transport_attempt BETWEEN 0 AND transport_limit",
    )
    op.create_check_constraint(
        "ck_provider_retry_classification",
        phase,
        "retry_classification IS NULL OR retry_classification IN ('BEFORE_DISPATCH','RETRYABLE_KNOWN','PERMANENT','UNKNOWN')",
    )
    op.create_table(
        "cw5_run_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("cw5_runs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("provider_phase_id", sa.Uuid(), sa.ForeignKey(phase + ".id")),
        sa.Column("attempt", sa.Integer()),
        sa.Column("from_state", sa.String(24)),
        sa.Column("to_state", sa.String(24)),
        sa.Column("retry_classification", sa.String(24)),
        sa.Column("error_class", sa.String(80)),
        sa.Column("latency_ms", sa.Numeric(16, 3)),
        sa.Column("usage", JSONB()),
    )
    op.create_index("ix_conversation_run_events", "cw5_run_events", ["run_id", "created_at"])
    op.execute("""
    CREATE FUNCTION cw5_retry_limit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.transport_limit IS DISTINCT FROM NEW.transport_limit
        OR NEW.transport_attempt < OLD.transport_attempt
      THEN RAISE EXCEPTION 'provider_retry_identity_immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw5_retry_limit_immutable BEFORE UPDATE ON cw4_provider_phases
      FOR EACH ROW EXECUTE FUNCTION cw5_retry_limit_immutable();

    CREATE FUNCTION cw5_execution_claim_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.execution_started_at IS NOT NULL AND OLD.execution_started_at IS DISTINCT FROM NEW.execution_started_at
      THEN RAISE EXCEPTION 'conversation_execution_claim_immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw5_execution_claim_immutable BEFORE UPDATE ON cw5_runs
      FOR EACH ROW EXECUTE FUNCTION cw5_execution_claim_immutable();

    CREATE FUNCTION cw5_acceptance_retained() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'conversation_acceptance_retained' USING ERRCODE='23514'; END $$;
    CREATE TRIGGER cw5_acceptance_retained BEFORE UPDATE OR DELETE ON cw5_acceptances
      FOR EACH ROW EXECUTE FUNCTION cw5_acceptance_retained();
    CREATE TRIGGER cw5_acceptance_no_truncate BEFORE TRUNCATE ON cw5_acceptances
      FOR EACH STATEMENT EXECUTE FUNCTION cw5_acceptance_retained();

    CREATE FUNCTION cw5_run_bundle_consistent() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE rid uuid; current_status text; has_result boolean;
    BEGIN
      IF TG_TABLE_NAME='cw5_runs' THEN rid:=NEW.id;
      ELSIF TG_OP='DELETE' THEN rid:=OLD.run_id;
      ELSE rid:=NEW.run_id; END IF;
      SELECT status INTO current_status FROM cw5_runs WHERE id=rid;
      SELECT EXISTS (SELECT 1 FROM cw5_acceptances WHERE run_id=rid) INTO has_result;
      IF current_status IS NOT NULL AND ((current_status='ACCEPTED') IS DISTINCT FROM has_result)
      THEN RAISE EXCEPTION 'conversation_result_status_conflict' USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER cw5_run_bundle_consistent AFTER INSERT OR UPDATE ON cw5_runs
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cw5_run_bundle_consistent();
    CREATE CONSTRAINT TRIGGER cw5_acceptance_bundle_consistent AFTER INSERT OR UPDATE OR DELETE ON cw5_acceptances
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cw5_run_bundle_consistent();

    CREATE FUNCTION cw5_run_event_retained() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'conversation_run_event_retained' USING ERRCODE='23514'; END $$;
    CREATE TRIGGER cw5_run_event_retained BEFORE UPDATE OR DELETE ON cw5_run_events
      FOR EACH ROW EXECUTE FUNCTION cw5_run_event_retained();
    CREATE TRIGGER cw5_run_event_no_truncate BEFORE TRUNCATE ON cw5_run_events
      FOR EACH STATEMENT EXECUTE FUNCTION cw5_run_event_retained();
    """)


def downgrade():
    raise RuntimeError("runtime_receipts_are_durable_use_fix_forward")
