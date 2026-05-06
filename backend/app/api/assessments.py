"""评估接口 —— 对应 OpenAPI 三个路径"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Advice as AdviceModel
from app.models import Assessment, Evidence, SymptomObservation
from app.rules.loader import RulesBundle, load_rules
from app.schemas.assessment import (
    Advice,
    AssessmentRequest,
    AssessmentResult,
    AssessmentSummary,
    AuditInfo,
    MatchedRule,
    ParsedSymptoms,
    SymptomItem,
)


logger = logging.getLogger(__name__)
router = APIRouter()


# ── 规则集缓存（模块级） ────────────────────────────────────────
# 仅用于在 GET 路径回查 rules.yaml 取 source_doc / urgency；
# 不重新评估、不影响业务决策。
_rules_bundle_cache: RulesBundle | None = None


def _get_rules_bundle() -> RulesBundle:
    global _rules_bundle_cache
    if _rules_bundle_cache is None:
        _rules_bundle_cache = load_rules(settings.rules_path)
    return _rules_bundle_cache


# ── 埋点（M7 未合入时容错） ────────────────────────────────────
def _emit_result_viewed(
    db: Session, assessment: Assessment, session_id: str = "N/A"
) -> None:
    """触发 result_viewed；M7 未合入或运行时失败均不阻塞主流程。"""
    try:
        from app.services.event_emitter import EventEmitter  # noqa: WPS433

        # M7 合入后 EventEmitter 构造签名可能是 EventEmitter(db) 或 EventEmitter()。
        # 两种都尝试，保持兼容。
        try:
            emitter = EventEmitter(db)  # type: ignore[call-arg]
        except TypeError:
            emitter = EventEmitter()
        emitter.emit(
            event_type="result_viewed",
            session_id=session_id,
            user_id=assessment.user_id,
            assessment_id=assessment.id,
            payload={"risk_level": assessment.risk_level},
        )
    except Exception:  # noqa: BLE001 —— 埋点永远不应阻塞 GET
        logger.exception("[assessments.get] result_viewed emit failed (non-fatal)")


# ── 数据库 → AssessmentResult 组装器 ─────────────────────────────
def _build_result_from_db(
    assessment: Assessment,
    advice_row: AdviceModel | None,
    evidence_rows: list[Evidence],
    obs_rows: list[SymptomObservation],
) -> AssessmentResult:
    """4 表联查后的纯函数组装。

    设计说明：
    - matched_rules: 来自 evidence 表（M6 已写入），source_doc 反查 rules.yaml
    - generated_at + rule_engine_version: 来自 assessment 主表
    - parsed_symptoms.symptoms: 优先从 symptom_observation 反构（事实之记）
      context: 从 assessment.parsed_symptoms JSONB 取 —— context 不持久化为列
    - urgency: 由首条命中规则的 advice_template 反查 rules.yaml；advice 表不存
    """
    bundle = _get_rules_bundle()
    rule_index = {r["id"]: r for r in bundle.rules}

    # ── 审计三件套 ────────────────────────────────────────────
    matched_rules = [
        MatchedRule(
            rule_id=ev.rule_id,
            rule_version=ev.rule_version,
            source_doc=rule_index.get(ev.rule_id, {}).get("source", ""),
            matched_fields=ev.matched_fields or {},
            rationale_text=ev.rationale_text,
        )
        for ev in evidence_rows
    ]

    # ── advice ──────────────────────────────────────────────
    primary_rule_id = matched_rules[0].rule_id if matched_rules else ""
    primary_rule_meta = rule_index.get(primary_rule_id, {})
    urgency = primary_rule_meta.get("urgency", "next_visit")

    advice = Advice(
        text=advice_row.rendered_text if advice_row else "",
        contact_team=bool(advice_row.contact_team) if advice_row else False,
        urgency=urgency,
    )

    # ── parsed_symptoms ─────────────────────────────────────
    raw_jsonb = assessment.parsed_symptoms or {}
    context = dict(raw_jsonb.get("context") or {})
    confidence_jsonb = raw_jsonb.get("confidence")

    if obs_rows:
        symptoms = [
            SymptomItem(
                symptom_id=o.symptom_id,
                numeric_value=float(o.numeric_value) if o.numeric_value is not None else None,
                numeric_unit=o.numeric_unit,
                categorical_value=o.categorical_value,
                ctcae_grade=o.ctcae_grade,
                duration_hours=float(o.duration_hours) if o.duration_hours is not None else None,
                interferes_with_adl=o.interferes_with_adl,
            )
            for o in obs_rows
        ]
    else:
        # 没有 observation 行时回退 JSONB（pending/failed 状态可能就是这种）
        symptoms = [
            SymptomItem.model_validate(s) for s in (raw_jsonb.get("symptoms") or [])
        ]

    parsed_symptoms = ParsedSymptoms(
        symptoms=symptoms,
        context=context,
        confidence=confidence_jsonb,
    )

    return AssessmentResult(
        assessment_id=assessment.id,
        created_at=assessment.created_at,
        # decision_status='pending'/'failed' 时 risk_level 可能为 NULL
        # MVP 约定：前端按 audit.matched_rules 是否为空判断；这里给个语义合法的占位
        risk_level=assessment.risk_level or "low",
        advice=advice,
        audit=AuditInfo(
            matched_rules=matched_rules,
            generated_at=assessment.created_at,
            rule_engine_version=assessment.rule_engine_version
            or bundle.engine_version,
            extraction_model_version=assessment.extraction_model_version,
        ),
        parsed_symptoms=parsed_symptoms,
    )


# ── 路由 ─────────────────────────────────────────────────────
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
    """获取单次评估结果 —— 4 表联查 → 组装 AssessmentResult。

    边界（DESIGN.md §7 / 任务卡 Part B）：
      - ID 不存在     → 404
      - status=pending/failed → 200 返回当前状态；前端按 audit.matched_rules 判断
      - 触发 result_viewed 埋点（失败不阻塞返回）
    """
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    evidence_rows: list[Evidence] = (
        db.query(Evidence)
        .filter(Evidence.assessment_id == assessment_id)
        .order_by(Evidence.matched_at.asc())
        .all()
    )
    advice_row: AdviceModel | None = (
        db.query(AdviceModel)
        .filter(AdviceModel.assessment_id == assessment_id)
        .order_by(AdviceModel.created_at.desc())
        .first()
    )
    obs_rows: list[SymptomObservation] = (
        db.query(SymptomObservation)
        .filter(SymptomObservation.assessment_id == assessment_id)
        .order_by(SymptomObservation.observed_at.asc())
        .all()
    )

    result = _build_result_from_db(assessment, advice_row, evidence_rows, obs_rows)

    # 埋点（M7 未合入时无副作用）
    _emit_result_viewed(db, assessment)

    return result


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
