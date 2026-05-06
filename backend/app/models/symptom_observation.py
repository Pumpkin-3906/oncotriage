"""症状观察 —— 决策实际依据的事实行（与 schema.sql 一一对应）

LLM 抽取后会把每个症状落库一行：
- 数值型（如 fever）填 numeric_value / numeric_unit
- 分级型（如 nausea）填 ctcae_grade 或 categorical_value
- 二元型直接存在即代表命中

注意 assessment.parsed_symptoms（JSONB）是审计冻结，
真正给规则引擎查的事实在本表 / context（context 暂存 JSON）。
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SymptomObservation(Base):
    __tablename__ = "symptom_observation"
    __table_args__ = (
        CheckConstraint("ctcae_grade BETWEEN 1 AND 5", name="chk_grade"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    symptom_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("symptom_dictionary.id"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    numeric_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    categorical_value: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ctcae_grade: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    onset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interferes_with_adl: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    extraction_source: Mapped[str] = mapped_column(String(16), nullable=False)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
