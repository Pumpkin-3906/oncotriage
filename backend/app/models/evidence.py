"""证据表 —— 审计核心（与 schema.sql 一一对应）

每命中一条规则就写一行 evidence。matched_fields(JSONB) 存命中时的具体值，
rationale_text 是规则的人类可读理由（暂朴素实现，未来可由 RAG 生成）。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(16), nullable=False)
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    matched_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rationale_text: Mapped[str] = mapped_column(Text, nullable=False)
