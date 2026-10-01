"""Evaluation-only campaign; no change to Conversation Acceptance semantics."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw6_dev_campaigns",
        sa.Column("id", sa.Uuid(), sa.ForeignKey("cw2_eval_runs.id"), primary_key=True),
        sa.Column("policy", JSONB, nullable=False),
        sa.Column("policy_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("active_case", sa.String(80)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stop_reason", sa.String(80)),
        sa.Column("review", JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "status IN ('DISABLED','ACTIVE','SYNTHETIC','STOPPED','COMPLETE')", name="ck_dev_campaign_status"
        ),
    )
    op.execute("""
    CREATE FUNCTION cw6_dev_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'dev_campaign_retained' USING ERRCODE='23514';
      END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status IS DISTINCT FROM (CASE NEW.policy->>'mode'
            WHEN 'DISABLED' THEN 'DISABLED' WHEN 'SYNTHETIC' THEN 'SYNTHETIC'
            WHEN 'HUMAN' THEN 'ACTIVE' ELSE NULL END)
          OR NEW.active_case IS NOT NULL
          OR EXISTS (SELECT 1 FROM cw4_provider_phases WHERE eval_run_id=NEW.id)
          OR EXISTS (SELECT 1 FROM cw2_eval_cases WHERE eval_run_id=NEW.id)
        THEN RAISE EXCEPTION 'dev_campaign_initial_identity' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF ROW(OLD.id, OLD.policy, OLD.policy_sha256, OLD.expires_at, OLD.deadline)
        IS DISTINCT FROM ROW(NEW.id, NEW.policy, NEW.policy_sha256, NEW.expires_at, NEW.deadline)
        OR (NEW.status <> OLD.status AND NOT
          (OLD.status IN ('ACTIVE','SYNTHETIC') AND NEW.status IN ('STOPPED','COMPLETE')))
      THEN RAISE EXCEPTION 'dev_campaign_immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw6_dev_immutable BEFORE INSERT OR UPDATE OR DELETE ON cw6_dev_campaigns
      FOR EACH ROW EXECUTE FUNCTION cw6_dev_immutable();
    CREATE TRIGGER cw6_dev_no_truncate BEFORE TRUNCATE ON cw6_dev_campaigns
      FOR EACH STATEMENT EXECUTE FUNCTION cw6_dev_immutable();
    CREATE FUNCTION cw6_dev_phase_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE old_dev boolean := false; new_dev boolean := false;
    BEGIN
      IF TG_OP='TRUNCATE' THEN
        IF EXISTS (SELECT 1 FROM cw6_dev_campaigns) THEN
          RAISE EXCEPTION 'dev_phase_retained' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
      IF TG_OP IN ('UPDATE','DELETE') THEN
        old_dev := EXISTS (SELECT 1 FROM cw6_dev_campaigns WHERE id=OLD.eval_run_id);
      END IF;
      IF TG_OP IN ('INSERT','UPDATE') THEN
        new_dev := EXISTS (SELECT 1 FROM cw6_dev_campaigns WHERE id=NEW.eval_run_id);
      END IF;
      IF TG_OP='DELETE' THEN
        IF old_dev THEN RAISE EXCEPTION 'dev_phase_retained' USING ERRCODE='23514'; END IF;
        RETURN OLD;
      END IF;
      IF old_dev OR new_dev THEN
        IF TG_OP='UPDATE' AND old_dev IS DISTINCT FROM new_dev THEN
          RAISE EXCEPTION 'dev_phase_ownership_boundary' USING ERRCODE='23514';
        END IF;
        IF NEW.case_id IS NULL OR NEW.phase_attempt <> 1
          OR NEW.phase NOT IN ('interpretation','generation')
          OR NEW.query_run_id IS NOT NULL OR NEW.conversation_run_id IS NOT NULL
          OR NEW.authorization_id IS NULL OR NEW.authorization_deadline IS NULL
          OR NEW.provider IS NULL OR NEW.model IS NULL OR NEW.price_revision IS NULL
          OR NEW.prompt_revision IS NULL OR NEW.request_hash IS NULL
          OR NEW.input_tokens IS NULL OR NEW.input_tokens <= 0
          OR NEW.output_tokens IS NULL OR NEW.output_tokens <= 0 OR NEW.reserved_yuan <= 0
          OR NEW.logical_key <> 'dev:' || NEW.eval_run_id::text || ':' || NEW.case_id || ':' || NEW.phase
        THEN RAISE EXCEPTION 'dev_phase_identity' USING ERRCODE='23514'; END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.state <> 'PREPARED' OR NEW.outcome <> 'not_dispatched' OR NEW.dispatched_at IS NOT NULL
            OR NEW.request_id IS NOT NULL OR NULLIF(NEW.usage,'null'::jsonb) IS NOT NULL
            OR NEW.estimated_yuan IS NOT NULL OR NEW.result_hash IS NOT NULL
            OR NULLIF(NEW.result,'null'::jsonb) IS NOT NULL OR NEW.error_code IS NOT NULL
          THEN RAISE EXCEPTION 'dev_phase_initial_state' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;
        IF OLD.state IN ('COMPLETED','UNKNOWN','REJECTED') AND NEW IS DISTINCT FROM OLD THEN
          RAISE EXCEPTION 'dev_phase_terminal_immutable' USING ERRCODE='23514';
        END IF;
        IF TG_OP='UPDATE' AND
          (ROW(OLD.id,OLD.eval_run_id,OLD.case_id,OLD.query_run_id,OLD.conversation_run_id,
              OLD.logical_key,OLD.reserved_at,OLD.created_at,OLD.phase,OLD.phase_attempt,OLD.owner,OLD.fence,
              OLD.authorization_id,OLD.authorization_deadline,OLD.request_hash,OLD.prompt_revision,
              OLD.input_tokens,OLD.output_tokens,OLD.reserved_yuan,OLD.provider,OLD.model,OLD.price_revision)
           IS DISTINCT FROM
           ROW(NEW.id,NEW.eval_run_id,NEW.case_id,NEW.query_run_id,NEW.conversation_run_id,
              NEW.logical_key,NEW.reserved_at,NEW.created_at,NEW.phase,NEW.phase_attempt,NEW.owner,NEW.fence,
              NEW.authorization_id,NEW.authorization_deadline,NEW.request_hash,NEW.prompt_revision,
              NEW.input_tokens,NEW.output_tokens,NEW.reserved_yuan,NEW.provider,NEW.model,NEW.price_revision)
           )
        THEN RAISE EXCEPTION 'dev_phase_immutable' USING ERRCODE='23514'; END IF;
        IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
        IF NOT ((OLD.state='PREPARED' AND NEW.state IN ('DISPATCHED','REJECTED'))
          OR (OLD.state='DISPATCHED' AND NEW.state IN ('COMPLETED','UNKNOWN','REJECTED')))
        THEN RAISE EXCEPTION 'dev_phase_transition' USING ERRCODE='23514'; END IF;
        IF (OLD.state='PREPARED' AND NEW.state='DISPATCHED' AND NEW.dispatched_at IS NULL)
          OR (NOT (OLD.state='PREPARED' AND NEW.state='DISPATCHED')
              AND NEW.dispatched_at IS DISTINCT FROM OLD.dispatched_at)
          OR (NEW.state='DISPATCHED' AND (NEW.outcome <> 'unknown'
              OR NEW.request_id IS NOT NULL OR NULLIF(NEW.usage,'null'::jsonb) IS NOT NULL
              OR NEW.estimated_yuan IS NOT NULL OR NEW.result_hash IS NOT NULL
              OR NULLIF(NEW.result,'null'::jsonb) IS NOT NULL OR NEW.error_code IS NOT NULL))
          OR (NEW.state='COMPLETED' AND (NEW.outcome <> 'known' OR NEW.result_hash IS NULL))
          OR (NEW.state='UNKNOWN' AND NEW.outcome <> 'unknown')
          OR (NEW.state='REJECTED' AND NEW.outcome <> 'known_not_executed')
        THEN RAISE EXCEPTION 'dev_phase_receipt_transition' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw6_dev_phase_immutable BEFORE INSERT OR UPDATE OR DELETE ON cw4_provider_phases
      FOR EACH ROW EXECUTE FUNCTION cw6_dev_phase_immutable();
    CREATE TRIGGER cw6_dev_phase_no_truncate BEFORE TRUNCATE ON cw4_provider_phases
      FOR EACH STATEMENT EXECUTE FUNCTION cw6_dev_phase_immutable();
    CREATE FUNCTION cw6_dev_result_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE old_dev boolean := false; new_dev boolean := false;
    BEGIN
      IF TG_OP='TRUNCATE' THEN
        IF EXISTS (SELECT 1 FROM cw6_dev_campaigns) THEN
          RAISE EXCEPTION 'dev_case_retained' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
      IF TG_OP IN ('UPDATE','DELETE') THEN
        old_dev := EXISTS (SELECT 1 FROM cw6_dev_campaigns WHERE id=OLD.eval_run_id);
      END IF;
      IF TG_OP IN ('INSERT','UPDATE') THEN
        new_dev := EXISTS (SELECT 1 FROM cw6_dev_campaigns WHERE id=NEW.eval_run_id);
      END IF;
      IF TG_OP='DELETE' THEN
        IF old_dev THEN RAISE EXCEPTION 'dev_case_retained' USING ERRCODE='23514'; END IF;
        RETURN OLD;
      END IF;
      IF old_dev OR new_dev THEN
        IF NEW.max_attempts <> 1 OR NEW.query_run_id IS NOT NULL THEN
          RAISE EXCEPTION 'dev_case_identity' USING ERRCODE='23514'; END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.status <> 'PENDING' OR NEW.execution_attempt <> 0 OR NEW.fence <> 0
            OR NEW.owner IS NOT NULL OR NEW.started_at IS NOT NULL OR NEW.completed_at IS NOT NULL
            OR NEW.active_deadline IS NOT NULL
          THEN RAISE EXCEPTION 'dev_case_initial_state' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;
        IF ROW(OLD.eval_run_id,OLD.case_id,OLD.max_attempts,OLD.created_at)
          IS DISTINCT FROM ROW(NEW.eval_run_id,NEW.case_id,NEW.max_attempts,NEW.created_at)
          OR old_dev IS DISTINCT FROM new_dev
          OR (OLD.status IN ('COMPLETED','FAILED','OUTCOME_UNKNOWN') AND NEW IS DISTINCT FROM OLD)
        THEN RAISE EXCEPTION 'dev_result_immutable' USING ERRCODE='23514'; END IF;
        IF OLD.status='PENDING' THEN
          IF NOT ((NEW.status='PENDING' AND NEW.execution_attempt=0 AND NEW.fence=0 AND NEW.owner IS NULL)
            OR (NEW.status='RUNNING' AND NEW.execution_attempt=1 AND NEW.fence=1 AND NEW.owner IS NOT NULL
                AND NEW.started_at IS NOT NULL AND NEW.active_deadline IS NOT NULL))
          THEN RAISE EXCEPTION 'dev_case_transition' USING ERRCODE='23514'; END IF;
        ELSIF OLD.status='RUNNING' THEN
          IF NEW.status NOT IN ('RUNNING','COMPLETED','FAILED','OUTCOME_UNKNOWN')
            OR ROW(OLD.owner,OLD.fence,OLD.execution_attempt,OLD.started_at,OLD.active_deadline)
              IS DISTINCT FROM ROW(NEW.owner,NEW.fence,NEW.execution_attempt,NEW.started_at,NEW.active_deadline)
            OR (NEW.status <> 'RUNNING' AND NEW.completed_at IS NULL)
          THEN RAISE EXCEPTION 'dev_case_transition' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw6_dev_result_immutable BEFORE INSERT OR UPDATE OR DELETE ON cw2_eval_cases
      FOR EACH ROW EXECUTE FUNCTION cw6_dev_result_immutable();
    CREATE TRIGGER cw6_dev_case_no_truncate BEFORE TRUNCATE ON cw2_eval_cases
      FOR EACH STATEMENT EXECUTE FUNCTION cw6_dev_result_immutable();
    """)


def downgrade():
    raise RuntimeError("dev_campaign_receipts_are_durable_use_fix_forward")
