"""评估主表"""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Numeric, ForeignKey, Text, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Assessment(Base):
    __tablename__ = "assessment"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('high','medium','low')", name="chk_risk"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 输入
    raw_input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_source: Mapped[str] = mapped_column(String(16), nullable=False)

    # LLM 抽取原始输出（审计用）
    parsed_symptoms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    extraction_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 决策结果
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    rule_engine_version: Mapped[str] = mapped_column(String(16), nullable=False)
    used_timeseries: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
