"""评估接口的 Pydantic schemas —— 与 docs/api/openapi.yaml 保持一致"""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


# ── 抽取结果（LLM 输出 / checklist 输入共用此结构）────────────
class SymptomItem(BaseModel):
    symptom_id: str
    numeric_value: float | None = None
    numeric_unit: str | None = None
    categorical_value: str | None = None
    ctcae_grade: int | None = Field(None, ge=1, le=5)
    duration_hours: float | None = None
    interferes_with_adl: bool | None = None


class ParsedSymptoms(BaseModel):
    symptoms: list[SymptomItem]
    context: dict = Field(default_factory=dict)
    confidence: float | None = Field(None, ge=0.0, le=1.0)


# ── 输入 ─────────────────────────────────────────────────────
class AssessmentRequest(BaseModel):
    user_id: UUID
    session_id: str
    input_source: Literal["free_text", "checklist_fallback"]
    # 幂等键 —— 同 (user_id, idempotency_key) 重复提交直接返回首次结果
    idempotency_key: str = Field(..., min_length=8, max_length=64)
    raw_input_text: str | None = Field(None, max_length=4000)
    checklist_payload: dict | None = None
    feature_flags: dict = Field(default_factory=dict)
    # MVP+1：用户在 extract 预览后确认/编辑过的结构化症状。
    # 传入则跳过 LLM 抽取，直接进规则引擎（向后兼容：不传仍走 LLM）。
    parsed_symptoms: ParsedSymptoms | None = None


# ── Extract（无状态预览）─────────────────────────────────────
class CompletenessInfo(BaseModel):
    is_complete: bool
    missing_slots: list[dict] = Field(default_factory=list)
    # 形如 [{"symptom_id": "fever", "missing_fields": ["numeric_value"]}]


class ExtractRequest(BaseModel):
    user_id: UUID
    input_source: Literal["free_text", "checklist"]
    raw_input_text: str | None = Field(None, max_length=4000)
    form_payload: dict | None = None  # checklist 时传，结构对应 ParsedSymptoms


class ExtractResponse(BaseModel):
    parsed_symptoms: "ParsedSymptoms"
    completeness: CompletenessInfo
    extraction_model_version: str


# ── 输出 ─────────────────────────────────────────────────────
class MatchedRule(BaseModel):
    rule_id: str
    rule_version: str
    source_doc: str
    matched_fields: dict
    rationale_text: str


class AuditInfo(BaseModel):
    """审计三件套：命中规则 + 时间 + 版本号"""
    matched_rules: list[MatchedRule]
    generated_at: datetime
    rule_engine_version: str
    extraction_model_version: str | None


class Advice(BaseModel):
    text: str
    contact_team: bool
    urgency: Literal["now_24h", "this_week", "next_visit"]


class AssessmentResult(BaseModel):
    assessment_id: UUID
    created_at: datetime
    risk_level: Literal["high", "medium", "low"]
    advice: Advice
    audit: AuditInfo
    parsed_symptoms: ParsedSymptoms


class AssessmentSummary(BaseModel):
    assessment_id: UUID
    created_at: datetime
    risk_level: str
    primary_symptom: str | None = None
