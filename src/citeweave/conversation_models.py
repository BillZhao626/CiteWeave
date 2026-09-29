"""Additive core tables; legacy QueryRun readers and tables stay unchanged."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
