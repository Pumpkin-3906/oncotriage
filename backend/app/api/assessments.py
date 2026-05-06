"""评估接口 —— 对应 OpenAPI 三个路径"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.assessment import (
    AssessmentRequest,
    AssessmentResult,
    AssessmentSummary,
)
from app.services.event_emitter import EventEmitter
from app.services.llm_extractor import LLMExtractionError
from app.services.orchestrator import Orchestrator

router = APIRouter()


@router.post("/assessments", response_model=AssessmentResult, status_code=201)
def submit_assessment(
    req: AssessmentRequest,
    db: Session = Depends(get_db),
) -> AssessmentResult:
    """提交评估 —— 触发 LLM 抽取 + 规则决策

    LLM 抽取失败 → 422 + ChecklistFallbackPrompt（前端据此切换到症状清单）
    """
    try:
        result = Orchestrator(db).run(req)
    except LLMExtractionError:
        # 422 + 前端可识别的 fallback 结构
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "low_confidence",
                "checklist_url": "/api/v1/checklist",
                "message": "无法解析您的描述，请使用症状清单",
            },
        )

    # 埋点：assessment_submitted（事务外，失败不影响主流程）
    EventEmitter(db).emit(
        event_type="assessment_submitted",
        session_id=req.session_id,
        user_id=req.user_id,
        assessment_id=result.assessment_id,
        payload={"input_length": len(req.raw_input_text or "")},
    )
    return result


@router.get("/assessments/{assessment_id}", response_model=AssessmentResult)
def get_assessment(
    assessment_id: UUID,
    db: Session = Depends(get_db),
) -> AssessmentResult:
    """获取单次评估结果"""
    # TODO: 实现，包括从 evidence/advice/symptom_observation 组装审计三件套
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/users/{user_id}/assessments", response_model=list[AssessmentSummary])
def list_assessments(
    user_id: UUID,
    limit: int = 20,
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> list[AssessmentSummary]:
    """获取用户历史评估（按时间倒序）"""
    # TODO: 实现游标分页
    raise HTTPException(status_code=501, detail="Not implemented")
