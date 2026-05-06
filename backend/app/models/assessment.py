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
            "risk_level IS NULL OR risk_level IN ('high','medium','low')",
            name="chk_risk",
        ),
        CheckConstraint(
            "decision_status IN ('pending','completed','failed')",
            name="chk_decision_status",
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

    # 幂等键 —— 同 (user_id, idempotency_key) 重复提交直接返回首次结果
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # 输入
    raw_input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_source: Mapped[str] = mapped_column(String(16), nullable=False)

    # LLM 抽取原始输出（审计用）
    parsed_symptoms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    extraction_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 决策结果（Plan C：抽取已存但决策可能未完成 → 允许 NULL）
    risk_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    rule_engine_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    used_timeseries: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 决策状态：'pending' | 'completed' | 'failed'
    decision_status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )
