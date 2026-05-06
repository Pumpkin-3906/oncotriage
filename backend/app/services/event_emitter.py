"""事件埋点 —— 5 个核心事件的统一出口

对应 DESIGN.md §9 可观测性
MVP 阶段写到 stdout + event_log 表；生产环境改 Kafka。

写入策略：
- 同步 INSERT + commit，独立于业务事务
- 写失败仅 stderr 日志，不影响主流程（埋点不能拖死业务）
- VALID_EVENTS 是契约白名单，未知事件直接抛 ValueError 防止字段漂移
"""
import json
import sys
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import settings


VALID_EVENTS = {
    "assessment_started",
    "assessment_submitted",
    "result_viewed",
    "contact_team_clicked",
    "assessment_closed",
}


class EventEmitter:
    def __init__(self, db: Session):
        self.db = db

    def emit(
        self,
        event_type: str,
        session_id: str,
        user_id: UUID | str | None = None,
        assessment_id: UUID | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if event_type not in VALID_EVENTS:
            raise ValueError(f"Invalid event_type: {event_type}")

        # 1. 写 DB —— 失败仅 stderr，不抛
        try:
            self.db.execute(
                sa.text(
                    """
                    INSERT INTO event_log
                        (event_type, user_id, session_id, assessment_id, payload, occurred_at)
                    VALUES (:t, :u, :s, :a, CAST(:p AS JSONB), NOW())
                    """
                ),
                {
                    "t": event_type,
                    "u": str(user_id) if user_id is not None else None,
                    "s": session_id,
                    "a": str(assessment_id) if assessment_id is not None else None,
                    "p": json.dumps(payload or {}),
                },
            )
            self.db.commit()
        except Exception as e:
            print(f"[event_emitter] DB write failed: {e}", file=sys.stderr)
            try:
                self.db.rollback()
            except Exception:
                pass

        # 2. 实时 sink（仪表盘 / 调试）
        if settings.event_sink == "stdout":
            print(f"[EVENT] {event_type} session={session_id}")
