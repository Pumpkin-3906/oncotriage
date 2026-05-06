"""事件埋点表 —— 5 个核心事件的行为日志（DESIGN.md §9）

与 schema.sql 中 event_log 表一一对应。
- 业务事实表（assessment / advice / evidence）和行为日志表（event_log）分离
- 此表 EventEmitter 写入，主流程失败仅记 stderr，不影响业务
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    client_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
