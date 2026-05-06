"""编排器 —— 串起 感知 → 决策 → 执行 三个环节

对应 DESIGN.md §4 的主路径数据流。

事务策略: Plan C —— 抽取与决策独立事务
  Tx1: 写入 assessment + symptom_observation (decision_status='pending')
  Tx2: 跑规则引擎，写入 evidence + advice，update assessment.decision_status='completed'
  → Tx2 失败也不影响 Tx1，已抽取症状不丢

幂等性: 通过 (user_id, idempotency_key) 唯一索引保证
  → 重复提交直接返回首次结果，不重新调 LLM

所有阈值从 settings 读取，不在此文件硬编码。
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.assessment import AssessmentRequest, AssessmentResult


class Orchestrator:
    def __init__(self, db: Session):
        self.db = db

    def run(self, req: AssessmentRequest, idempotency_key: str) -> AssessmentResult:
        # ── Step 0: 幂等检查 ──────────────────────────────────
        # TODO: SELECT * FROM assessment WHERE user_id=? AND idempotency_key=?
        # 命中则直接返回历史 AssessmentResult（重新组装 audit）

        # ── Step 1 (Tx1): 感知 + 写入抽取结果 ────────────────
        # try:
        #     parsed = LLMExtractor().extract(req.raw_input_text, dictionary)
        # except LLMExtractionError:
        #     return self._respond_with_checklist_fallback()
        #
        # with self.db.begin():
        #     assessment = Assessment(
        #         ...,
        #         idempotency_key=idempotency_key,
        #         parsed_symptoms=parsed.dict(),
        #         decision_status='pending',
        #     )
        #     self.db.add(assessment)
        #     for sym in parsed.symptoms:
        #         self.db.add(SymptomObservation(...))
        #
        # # 自动 bad case：低置信度
        # if parsed.confidence is not None and parsed.confidence < settings.low_confidence_threshold:
        #     self._flag_for_review(assessment.id, "auto_low_confidence",
        #                           {"confidence": parsed.confidence,
        #                            "threshold": settings.low_confidence_threshold})

        # ── Step 2 (Tx2): 决策 + 写入 evidence/advice ────────
        # try:
        #     trends = self._load_trends(...) if settings.feature_timeseries else None
        #     result = RuleEngine(rules).evaluate(parsed, trends)  # Plan D
        # except Exception:
        #     # 决策失败：标记 status=failed，触发 bad case
        #     with self.db.begin():
        #         assessment.decision_status = 'failed'
        #     self._flag_for_review(assessment.id, "auto_extraction_failed", {...})
        #     raise
        #
        # with self.db.begin():
        #     for match in result.all_matches:
        #         self.db.add(Evidence(rule_id=match.rule_id, ...))
        #     advice_text = AdviceRenderer(...).render(...)
        #     self.db.add(Advice(rendered_text=advice_text, ...))
        #     assessment.risk_level = result.final_risk_level
        #     assessment.decision_status = 'completed'
        #
        # # 自动 bad case：兜底规则触发
        # if any(m.rule_id == "R999_default_unmatched" for m in result.all_matches):
        #     self._flag_for_review(assessment.id, "auto_default_rule_hit", {...})

        # ── Step 3: 返回 + 埋点 ──────────────────────────────
        # event_emitter.emit("assessment_submitted", ...)
        # return AssessmentResult(...)

        raise NotImplementedError

    def _flag_for_review(
        self,
        assessment_id,
        trigger_source: str,
        payload: dict,
    ) -> None:
        """写入 case_review 表 —— L3 学习闭环的入口

        TODO: 实现 INSERT INTO case_review。
        建议事务外执行（失败不影响主流程）。
        """
        pass
