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
      IF ROW(OLD.id, OLD.policy, OLD.policy_sha256, OLD.expires_at, OLD.deadline)
        IS DISTINCT FROM ROW(NEW.id, NEW.policy, NEW.policy_sha256, NEW.expires_at, NEW.deadline)
        OR (OLD.status IN ('DISABLED','STOPPED','COMPLETE') AND NEW.status <> OLD.status)
      THEN RAISE EXCEPTION 'dev_campaign_immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw6_dev_immutable BEFORE UPDATE ON cw6_dev_campaigns
      FOR EACH ROW EXECUTE FUNCTION cw6_dev_immutable();
    CREATE FUNCTION cw6_dev_phase_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (SELECT 1 FROM cw6_dev_campaigns WHERE id=NEW.eval_run_id) THEN
        IF NEW.phase_attempt <> 1 OR NEW.query_run_id IS NOT NULL OR NEW.conversation_run_id IS NOT NULL
          OR NEW.authorization_id IS NULL OR NEW.input_tokens IS NULL OR NEW.output_tokens IS NULL
        THEN RAISE EXCEPTION 'dev_phase_identity' USING ERRCODE='23514'; END IF;
        IF TG_OP='UPDATE' AND
          (ROW(OLD.id,OLD.eval_run_id,OLD.case_id,OLD.phase,OLD.phase_attempt,OLD.owner,OLD.fence,
              OLD.authorization_id,OLD.authorization_deadline,OLD.request_hash,OLD.prompt_revision,
              OLD.input_tokens,OLD.output_tokens,OLD.reserved_yuan,OLD.provider,OLD.model,OLD.price_revision)
           IS DISTINCT FROM
           ROW(NEW.id,NEW.eval_run_id,NEW.case_id,NEW.phase,NEW.phase_attempt,NEW.owner,NEW.fence,
              NEW.authorization_id,NEW.authorization_deadline,NEW.request_hash,NEW.prompt_revision,
              NEW.input_tokens,NEW.output_tokens,NEW.reserved_yuan,NEW.provider,NEW.model,NEW.price_revision)
           OR OLD.state IN ('COMPLETED','UNKNOWN','REJECTED') AND NEW.state <> OLD.state)
        THEN RAISE EXCEPTION 'dev_phase_immutable' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw6_dev_phase_immutable BEFORE INSERT OR UPDATE ON cw4_provider_phases
      FOR EACH ROW EXECUTE FUNCTION cw6_dev_phase_immutable();
    CREATE FUNCTION cw6_dev_result_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (SELECT 1 FROM cw6_dev_campaigns WHERE id=OLD.eval_run_id)
        AND OLD.status IN ('COMPLETED','FAILED','OUTCOME_UNKNOWN') AND NEW IS DISTINCT FROM OLD
      THEN RAISE EXCEPTION 'dev_result_immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw6_dev_result_immutable BEFORE UPDATE ON cw2_eval_cases
      FOR EACH ROW EXECUTE FUNCTION cw6_dev_result_immutable();
    """)


def downgrade():
    raise RuntimeError("dev_campaign_receipts_are_durable_use_fix_forward")
