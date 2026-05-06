"""协同请求接口"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter()


class ContactRequestPayload(BaseModel):
    assessment_id: UUID
    urgency: str  # 'now_24h' | 'this_week' | 'next_visit'
    note_from_user: str | None = None


class ContactRequestResponse(BaseModel):
    contact_request_id: UUID
    status: str
    expected_response_time_hours: int


@router.post(
    "/contact-requests",
    response_model=ContactRequestResponse,
    status_code=201,
)
def create_contact_request(
    payload: ContactRequestPayload,
    db: Session = Depends(get_db),
) -> ContactRequestResponse:
    """创建联系团队请求 —— 同时触发 contact_team_clicked 埋点"""
    # TODO: 写入 contact_request 表 + 发起 event_log
    raise HTTPException(status_code=501, detail="Not implemented")
