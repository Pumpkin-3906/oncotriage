"""编排器 —— 串起 感知 → 决策 → 执行 三个环节

对应 DESIGN.md §4 主路径数据流。

事务策略 Plan C —— 抽取与决策独立事务（DESIGN.md §3 决策 #6）：
  Tx1: 写入 assessment + symptom_observation (decision_status='pending')
  Tx2: 跑规则引擎，写入 evidence + advice，update assessment.decision_status='completed'
  → Tx2 失败也不影响 Tx1，已抽取症状不丢

幂等性: (user_id, idempotency_key) 唯一索引（DESIGN.md §15）。
重复提交直接返回首次结果，不再调 LLM、不再写库。

错误传播：
  - LLMExtractionError      → 不写库，raise
  - Tx1 数据库错误          → 不写库，raise
  - 规则引擎异常 / Tx2 错误 → 标 decision_status='failed' 后 raise

CompletenessChecker 仅日志（v2 才返回 ClarificationNeeded）。
EventEmitter / case_review 写入留给 M7。
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Advice as AdviceModel
from app.models import Assessment, Evidence, SymptomObservation
from app.rules.loader import RulesBundle, load_rules
from app.schemas.assessment import (
    Advice,
    AssessmentRequest,
    AssessmentResult,
    AuditInfo,
    MatchedRule,
    ParsedSymptoms,
)
from app.services.completeness_checker import CompletenessChecker
from app.services.llm_extractor import LLMExtractor
from app.services.rule_engine import EvaluationResult, RuleEngine, RuleMatch


logger = logging.getLogger(__name__)


class Orchestrator:
    """单一入口的评估编排器。每次 HTTP 请求构造一个新实例（持有 db Session）。

    extractor / rules_bundle 可注入用于单测；生产路径下默认按 settings 自动构造。
    """

    def __init__(
        self,
        db: Session,
        extractor: LLMExtractor | None = None,
        rules_bundle: RulesBundle | None = None,
    ) -> None:
        self.db = db
        self._extractor = extractor
        self._rules_bundle = rules_bundle

    # ── 公开入口 ─────────────────────────────────────────────────
    def run(self, req: AssessmentRequest) -> AssessmentResult:
        existing = self._lookup_existing(req.user_id, req.idempotency_key)
        if existing is not None and existing.decision_status == "completed":
            logger.info(
                "[orchestrator] idempotency hit user=%s assessment=%s",
                req.user_id, existing.id,
            )
            return self._rebuild_result_from_db(existing)

        dictionary = self._load_dictionary()
        bundle = self._get_rules_bundle()

        # Tx1: 抽取 + 写 assessment + symptom_observation
        parsed = self._get_extractor().extract(req.raw_input_text or "", dictionary)
        assessment = self._persist_extraction(req, parsed)

        # 完整性检查：MVP 仅日志，不阻塞流程
        completeness = CompletenessChecker(dictionary).check(parsed)
        if not completeness.is_complete:
            # TODO(v2): 改为返回 ClarificationNeeded 让前端追问
            logger.info(
                "[completeness] incomplete missing_slots=%s",
                [(m.symptom_id, m.missing_fields) for m in completeness.missing_slots],
            )

        # Tx2: 规则评估 + 写 evidence/advice + 更新状态
        try:
            eval_result = RuleEngine(bundle.rules, bundle.engine_version).evaluate(parsed)
            self._persist_decision(assessment, eval_result, bundle)
        except Exception:
            self._mark_decision_failed(assessment.id)
            raise

        return self._build_result(assessment, eval_result, parsed, bundle)

    # ── 资源加载 ─────────────────────────────────────────────────
    def _lookup_existing(self, user_id, idempotency_key: str) -> Assessment | None:
        return (
            self.db.query(Assessment)
            .filter(
                Assessment.user_id == user_id,
                Assessment.idempotency_key == idempotency_key,
            )
            .first()
        )

    def _load_dictionary(self) -> list[dict]:
        rows = self.db.execute(
            sa.text(
                "SELECT id, display_name_zh, value_type, grading_scheme, aliases_zh "
                "FROM symptom_dictionary"
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    def _get_rules_bundle(self) -> RulesBundle:
        if self._rules_bundle is None:
            self._rules_bundle = load_rules(settings.rules_path)
        return self._rules_bundle

    def _get_extractor(self) -> LLMExtractor:
        if self._extractor is None:
            self._extractor = LLMExtractor()
        return self._extractor

    # ── Tx1 持久化 ──────────────────────────────────────────────
    def _persist_extraction(
        self, req: AssessmentRequest, parsed: ParsedSymptoms
    ) -> Assessment:
        """Tx1：写 assessment + symptom_observation；失败回滚由调用方 raise。

        显式 commit/rollback 而非 `with db.begin()` —— Session 默认 autobegin，
        外层 fixture 可能已开过事务，contextmanager 会撞 'transaction already begun'。
        """
        extractor_model = self._get_extractor().model
        try:
            assessment = Assessment(
                user_id=req.user_id,
                idempotency_key=req.idempotency_key,
                raw_input_text=req.raw_input_text or "",
                input_source=req.input_source,
                parsed_symptoms=parsed.model_dump(),
                extraction_confidence=parsed.confidence,
                extraction_model_version=extractor_model,
                used_timeseries=False,
                decision_status="pending",
            )
            self.db.add(assessment)
            self.db.flush()
            for sym in parsed.symptoms:
                self.db.add(SymptomObservation(
                    assessment_id=assessment.id,
                    user_id=req.user_id,
                    symptom_id=sym.symptom_id,
                    numeric_value=sym.numeric_value,
                    numeric_unit=sym.numeric_unit,
                    categorical_value=sym.categorical_value,
                    ctcae_grade=sym.ctcae_grade,
                    duration_hours=sym.duration_hours,
                    interferes_with_adl=sym.interferes_with_adl,
                    extraction_source="llm",
                    extraction_confidence=parsed.confidence,
                ))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(assessment)
        return assessment

    # ── Tx2 持久化 ──────────────────────────────────────────────
    def _persist_decision(
        self,
        assessment: Assessment,
        eval_result: EvaluationResult,
        bundle: RulesBundle,
    ) -> None:
        rendered_text = self._render_advice(eval_result.primary, assessment, bundle)
        try:
            for match in eval_result.all_matches:
                self.db.add(Evidence(
                    assessment_id=assessment.id,
                    rule_id=match.rule_id,
                    rule_version=match.rule_version,
                    matched_fields=match.matched_fields,
                    rationale_text=match.rationale_text,
                ))
            tpl_meta = bundle.advice_templates.get(eval_result.primary.advice_template, {})
            self.db.add(AdviceModel(
                assessment_id=assessment.id,
                template_id=eval_result.primary.advice_template,
                template_version=tpl_meta.get("version", "1.0.0"),
                rendered_text=rendered_text,
                contact_team=eval_result.primary.contact_team,
            ))
            assessment.risk_level = eval_result.final_risk_level
            assessment.rule_engine_version = bundle.engine_version
            assessment.used_timeseries = eval_result.used_timeseries
            assessment.decision_status = "completed"
            self.db.add(assessment)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _render_advice(
        match: RuleMatch, assessment: Assessment, bundle: RulesBundle
    ) -> str:
        """MVP: 简单 .replace()，不引 Jinja2（advice_renderer.py 是 v2 任务）。"""
        tpl = bundle.advice_templates.get(match.advice_template, {})
        text: str = tpl.get("text", "")
        return text.replace("{{assessment_id}}", str(assessment.id))

    def _mark_decision_failed(self, assessment_id) -> None:
        """决策阶段失败时调用 —— 独立事务，rollback 后再开新事务写状态。"""
        try:
            self.db.rollback()  # 清掉 Tx2 失败留下的脏状态（若有）
            self.db.execute(
                sa.update(Assessment)
                .where(Assessment.id == assessment_id)
                .values(decision_status="failed")
            )
            self.db.commit()
        except Exception:  # pragma: no cover - 标记本身失败不应再覆盖主异常
            logger.exception("[orchestrator] mark_decision_failed itself failed")
            self.db.rollback()

    # ── 组装 ─────────────────────────────────────────────────────
    def _build_result(
        self,
        assessment: Assessment,
        eval_result: EvaluationResult,
        parsed: ParsedSymptoms,
        bundle: RulesBundle,
    ) -> AssessmentResult:
        rendered_text = self._render_advice(eval_result.primary, assessment, bundle)
        return AssessmentResult(
            assessment_id=assessment.id,
            created_at=assessment.created_at,
            risk_level=eval_result.final_risk_level,
            advice=Advice(
                text=rendered_text,
                contact_team=eval_result.primary.contact_team,
                urgency=eval_result.primary.urgency,
            ),
            audit=AuditInfo(
                matched_rules=[
                    MatchedRule(
                        rule_id=m.rule_id,
                        rule_version=m.rule_version,
                        source_doc=m.source_doc,
                        matched_fields=m.matched_fields,
                        rationale_text=m.rationale_text,
                    ) for m in eval_result.all_matches
                ],
                generated_at=assessment.created_at,
                rule_engine_version=bundle.engine_version,
                extraction_model_version=assessment.extraction_model_version,
            ),
            parsed_symptoms=parsed,
        )

    def _rebuild_result_from_db(self, assessment: Assessment) -> AssessmentResult:
        """幂等命中路径：从 evidence/advice 反查重建结果，不重新调 LLM。"""
        evidences = (
            self.db.query(Evidence)
            .filter(Evidence.assessment_id == assessment.id)
            .all()
        )
        advice_row = (
            self.db.query(AdviceModel)
            .filter(AdviceModel.assessment_id == assessment.id)
            .order_by(AdviceModel.created_at.desc())
            .first()
        )
        bundle = self._get_rules_bundle()
        rule_index = {r["id"]: r for r in bundle.rules}

        matched_rules = [
            MatchedRule(
                rule_id=ev.rule_id,
                rule_version=ev.rule_version,
                source_doc=rule_index.get(ev.rule_id, {}).get("source", ""),
                matched_fields=ev.matched_fields or {},
                rationale_text=ev.rationale_text,
            ) for ev in evidences
        ]
        primary_id = matched_rules[0].rule_id if matched_rules else ""
        primary_meta = rule_index.get(primary_id, {})

        return AssessmentResult(
            assessment_id=assessment.id,
            created_at=assessment.created_at,
            risk_level=assessment.risk_level or "low",
            advice=Advice(
                text=advice_row.rendered_text if advice_row else "",
                contact_team=advice_row.contact_team if advice_row else False,
                urgency=primary_meta.get("urgency", "next_visit"),
            ),
            audit=AuditInfo(
                matched_rules=matched_rules,
                generated_at=assessment.created_at,
                rule_engine_version=assessment.rule_engine_version or bundle.engine_version,
                extraction_model_version=assessment.extraction_model_version,
            ),
            parsed_symptoms=ParsedSymptoms.model_validate(
                assessment.parsed_symptoms or {"symptoms": [], "context": {}}
            ),
        )
