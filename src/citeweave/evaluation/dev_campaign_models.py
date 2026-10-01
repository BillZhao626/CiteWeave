"""DEV-only immutable policy envelope; existing Eval/phase tables hold outcomes."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from citeweave.domain import Base


class DevCampaignRow(Base):
    __tablename__ = "cw6_dev_campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DISABLED','ACTIVE','SYNTHETIC','STOPPED','COMPLETE')",
            name="ck_dev_campaign_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(ForeignKey("cw2_eval_runs.id"), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSONB)
    policy_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    active_case: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(80))
    review: Mapped[dict] = mapped_column(JSONB, default=dict)
