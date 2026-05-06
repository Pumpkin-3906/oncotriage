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

router = APIRouter()


@router.post("/assessments", response_model=AssessmentResult, status_code=201)
def submit_assessment(
    req: AssessmentRequest,
    db: Session = Depends(get_db),
) -> AssessmentResult:
    """提交评估 —— 触发 LLM 抽取 + 规则决策"""
    # TODO: 调用 Orchestrator.run(req, db)
    raise HTTPException(status_code=501, detail="Not implemented")


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
