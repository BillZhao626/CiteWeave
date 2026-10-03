"""Additive core tables; legacy QueryRun readers and tables stay unchanged."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from citeweave.domain import Base


class ConversationRow(Base):
    __tablename__ = "cw5_conversations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key"),
        CheckConstraint("fence >= 0", name="ck_conversation_fence"),
        ForeignKeyConstraint(
            ["id", "head_id"],
            ["cw5_acceptances.conversation_id", "cw5_acceptances.id"],
            name="fk_conversation_head",
            use_alter=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column()
    key: Mapped[str] = mapped_column(String(128))
    head_id: Mapped[UUID | None] = mapped_column()
    fence: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationTurnRow(Base):
    __tablename__ = "cw5_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "id"),
        ForeignKeyConstraint(
            ["conversation_id", "expected_head"],
            ["cw5_acceptances.conversation_id", "cw5_acceptances.id"],
            name="fk_turn_input_snapshot",
            use_alter=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("cw5_conversations.id"))
    expected_head: Mapped[UUID | None] = mapped_column()
    request: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationRunRow(Base):
    __tablename__ = "cw5_runs"
    __table_args__ = (
        UniqueConstraint("authorization_id", name="uq_conversation_run_authorization"),
        CheckConstraint(
            "(authorization_id IS NULL AND authorization_deadline IS NULL AND "
            "authorization_max_calls IS NULL AND authorization_input_tokens IS NULL AND "
            "authorization_output_tokens IS NULL AND authorization_yuan IS NULL) OR "
            "(authorization_id IS NOT NULL AND authorization_deadline IS NOT NULL AND "
            "authorization_max_calls IS NOT NULL AND authorization_max_calls >= 0 AND "
            "authorization_input_tokens IS NOT NULL AND authorization_input_tokens >= 0 AND "
            "authorization_output_tokens IS NOT NULL AND authorization_output_tokens >= 0 AND "
            "authorization_yuan IS NOT NULL AND authorization_yuan >= 0)",
            name="ck_conversation_run_authorization",
        ),
        UniqueConstraint("conversation_id", "key"),
        UniqueConstraint("conversation_id", "turn_id", "id"),
        UniqueConstraint("retry_of"),
        ForeignKeyConstraint(["conversation_id", "turn_id"], ["cw5_turns.conversation_id", "cw5_turns.id"]),
        ForeignKeyConstraint(
            ["conversation_id", "turn_id", "retry_of"],
            ["cw5_runs.conversation_id", "cw5_runs.turn_id", "cw5_runs.id"],
        ),
        CheckConstraint("fence > 0", name="ck_conversation_run_fence"),
        CheckConstraint(
            "status IN ('ADMITTED','ACCEPTED','FAILED','CANCELLED','INTERRUPTED','UNKNOWN','STALE')",
            name="ck_conversation_run_status",
        ),
        CheckConstraint(
            "(status = 'ADMITTED') = (completed_at IS NULL)", name="ck_conversation_run_completion"
        ),
        Index(
            "uq_conversation_active_run",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'ADMITTED'"),
        ),
        Index("ix_conversation_turn_runs", "turn_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("cw5_conversations.id"))
    turn_id: Mapped[UUID] = mapped_column()
    retry_of: Mapped[UUID | None] = mapped_column()
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    owner: Mapped[UUID] = mapped_column()
    fence: Mapped[int] = mapped_column()
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    authorization_id: Mapped[UUID | None] = mapped_column()
    authorization_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_max_calls: Mapped[int | None] = mapped_column(Integer)
    authorization_input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    authorization_output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    authorization_yuan: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationRunEventRow(Base):
    __tablename__ = "cw5_run_events"
    __table_args__ = (Index("ix_conversation_run_events", "run_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("cw5_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(40))
    fence: Mapped[int] = mapped_column(Integer)
    provider_phase_id: Mapped[UUID | None] = mapped_column(ForeignKey("cw4_provider_phases.id"))
    attempt: Mapped[int | None] = mapped_column(Integer)
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str | None] = mapped_column(String(24))
    retry_classification: Mapped[str | None] = mapped_column(String(24))
    error_class: Mapped[str | None] = mapped_column(String(80))
    latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    usage: Mapped[dict | None] = mapped_column(JSONB)


class ConversationAcceptanceRow(Base):
    __tablename__ = "cw5_acceptances"
    __table_args__ = (
        UniqueConstraint("turn_id"),
        UniqueConstraint("run_id"),
        UniqueConstraint("conversation_id", "id"),
        ForeignKeyConstraint(
            ["conversation_id", "turn_id", "run_id"],
            ["cw5_runs.conversation_id", "cw5_runs.turn_id", "cw5_runs.id"],
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("cw5_conversations.id"))
    turn_id: Mapped[UUID] = mapped_column()
    run_id: Mapped[UUID] = mapped_column()
    result: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
