"""事件埋点 —— 5 个核心事件的统一出口

对应 DESIGN.md §9 可观测性
MVP 阶段写到 stdout + event_log 表；生产环境改 Kafka。
"""
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from app.config import settings


VALID_EVENTS = {
    "assessment_started",
    "assessment_submitted",
    "result_viewed",
    "contact_team_clicked",
    "assessment_closed",
}


class EventEmitter:
    def emit(
        self,
        event_type: str,
        session_id: str,
        user_id: UUID | None = None,
        assessment_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """
        TODO: 实现要点
        1. 校验 event_type ∈ VALID_EVENTS
        2. 写入 event_log 表（事务外，失败不影响主流程）
        3. 同时写到 EVENT_SINK (stdout / kafka) 用于实时仪表盘
        """
        if event_type not in VALID_EVENTS:
            raise ValueError(f"Invalid event_type: {event_type}")
        # ... 待实现
        record = {
            "event_type": event_type,
            "session_id": session_id,
            "user_id": str(user_id) if user_id else None,
            "assessment_id": str(assessment_id) if assessment_id else None,
            "occurred_at": datetime.utcnow().isoformat(),
            "payload": payload or {},
        }
        if settings.event_sink == "stdout":
            print(f"[EVENT] {json.dumps(record)}")
